//! Screen de `[N] CONFIGURAR`.
//!
//! El daemon es dueño de toda la config (ver `protocol::ConfigPayload` y
//! docs/adr/0001) — este módulo no conoce los campos de
//! `llama`/`understory`/`pithagoras`/`moe` por su nombre, los recorre
//! genéricamente igual que el daemon recorre `config._ENTRIES`. `install`
//! queda fuera de esta screen a propósito, aunque el `GET /config` del
//! daemon lo traiga igual — acá simplemente no se itera.
//!
//! Agrupación por función técnica (Sampling/Cache/Cómputo/Speculative/
//! General) es una decisión del **cliente**, no del daemon: `ConfigField.group`
//! viaja como string plano y NO llega en orden contiguo por grupo (ver
//! `config.py::LLAMA_FIELDS` — `context_window` es "general" entre dos
//! campos "compute", por ejemplo), así que `detail_rows` bucketea por grupo
//! en vez de solo detectar transiciones. Sub-configs con `group == ""`
//! (`understory`/`pithagoras`/`moe`, pocos campos) caen a una lista plana
//! sin headers.

use std::collections::HashMap;

use crossterm::event::KeyCode;
use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph};
use ratatui::Frame;
use tokio::sync::mpsc;

use crate::app::{App, AppEvent};
use crate::protocol::{ConfigField, ConfigPayload};

/// Orden de despliegue de los grupos de `llama` — no es el orden en que
/// llegan los campos (ver doc-comment del módulo), así que `detail_rows`
/// itera esta lista en vez de la de `fields` para decidir dónde va cada
/// header.
const GROUP_ORDER: &[(&str, &str)] = &[
    ("general", "GENERAL"),
    ("sampling", "SAMPLING"),
    ("cache", "CACHE / KV"),
    ("compute", "CÓMPUTO"),
    ("speculative", "SPECULATIVE DECODING"),
];

/// Qué panel recibe las teclas de navegación.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ConfigFocus {
    Services,
    Detail,
}

/// Resultado del último `POST /config` — separado de
/// `last_command_result`/`last_command_error` de `App` (que asumen el shape
/// `CommandResult` de boot/terminate/reload/install) porque `/config` tiene
/// su propio shape (`ok`/`written`/`warnings`/`errors`).
pub enum ConfigSaveStatus {
    Saved(String),
    Failed(String),
}

/// Todo el estado de `ScreenId::Settings`, agrupado para no mezclarse con el
/// resto de los campos de `App` (menú/monitor/effects/farewell) — agregar un
/// campo de configuración nuevo toca solo este struct, no `App` entero.
pub struct SettingsState {
    /// `GET /config` en curso o ya resuelto — `None` mientras carga (ver
    /// `draw`, que pinta "cargando…" en ese caso).
    pub payload: Option<ConfigPayload>,
    pub selected_service: usize,
    /// Índice dentro de `detail_rows(&service.fields)` del servicio
    /// seleccionado — se resetea a la primera fila seleccionable cada vez
    /// que cambia `selected_service`.
    pub selected_row: usize,
    pub focus: ConfigFocus,
    /// `Some(buffer)` mientras se edita el campo de texto seleccionado;
    /// `None` en modo navegación.
    pub editing: Option<String>,
    /// env var -> valor nuevo (string), todo lo tocado en esta sesión de
    /// settings — `config.diff_overrides` del lado daemon filtra qué de
    /// esto es un cambio real recién al guardar.
    pub edits: HashMap<String, String>,
    pub save_in_flight: bool,
    pub status: Option<ConfigSaveStatus>,
}

impl Default for SettingsState {
    fn default() -> Self {
        SettingsState {
            payload: None,
            selected_service: 0,
            selected_row: 0,
            focus: ConfigFocus::Services,
            editing: None,
            edits: HashMap::new(),
            save_in_flight: false,
            status: None,
        }
    }
}

pub enum DetailRow {
    Header(&'static str),
    /// Índice dentro de `service.fields` (no de esta lista).
    Field(usize),
}

/// Bucketea `fields` por `ConfigField.group` en el orden de `GROUP_ORDER`,
/// agrega un `Header` antes de cada bucket no vacío, y agrega al final (sin
/// header) los campos con `group == ""` — mismo criterio que
/// `understory`/`pithagoras`/`moe`, que no lo necesitan (pocos campos).
pub fn detail_rows(fields: &[ConfigField]) -> Vec<DetailRow> {
    let mut rows = Vec::new();
    for (group, label) in GROUP_ORDER {
        let idxs: Vec<usize> =
            fields.iter().enumerate().filter(|(_, f)| f.group == *group).map(|(i, _)| i).collect();
        if idxs.is_empty() {
            continue;
        }
        rows.push(DetailRow::Header(label));
        rows.extend(idxs.into_iter().map(DetailRow::Field));
    }
    rows.extend(
        fields.iter().enumerate().filter(|(_, f)| f.group.is_empty()).map(|(i, _)| DetailRow::Field(i)),
    );
    rows
}

/// Próxima fila seleccionable (`Field`, salta `Header`) a partir de (sin
/// incluir) `from` — se queda en `from` si ya es la última. Mismo criterio
/// de "tope" que `screens::next_selectable`, versión local porque esta
/// lista es propia de la screen (no un registro global como `MENU_ENTRIES`).
pub fn next_row(rows: &[DetailRow], from: usize) -> usize {
    rows.iter()
        .enumerate()
        .skip(from + 1)
        .find(|(_, r)| matches!(r, DetailRow::Field(_)))
        .map(|(i, _)| i)
        .unwrap_or(from)
}

pub fn prev_row(rows: &[DetailRow], from: usize) -> usize {
    rows[..from.min(rows.len())]
        .iter()
        .enumerate()
        .rev()
        .find(|(_, r)| matches!(r, DetailRow::Field(_)))
        .map(|(i, _)| i)
        .unwrap_or(from)
}

pub fn first_row(rows: &[DetailRow]) -> usize {
    rows.iter().position(|r| matches!(r, DetailRow::Field(_))).unwrap_or(0)
}

/// Valor efectivo de un campo — el edit en curso (`app.settings.edits`) si lo
/// tocaste esta sesión, si no el que trajo el `GET /config`.
pub fn field_value<'a>(app: &'a App, field: &'a ConfigField) -> &'a str {
    app.settings.edits.get(&field.env).map(String::as_str).unwrap_or(&field.value)
}

/// Toda la lógica de teclado de `ScreenId::Settings` — vive acá (no en
/// `app.rs`) porque necesita mutar `App::settings` y disparar `POST /config`
/// (`crate::app::save_config`). Consume la tecla entera, no cae al catch-all
/// `q`=salir del loop principal: mientras se edita un campo de texto,
/// cualquier char (incluido 'q') es contenido del campo, no un atajo —
/// mismo criterio de "q/Esc = volver, no salir" que la screen de Logs.
pub fn handle_key(app: &mut App, code: KeyCode, tx: &mpsc::UnboundedSender<AppEvent>) {
    if app.settings.editing.is_none() && matches!(code, KeyCode::Char('q') | KeyCode::Esc) {
        app.screen = super::ScreenId::Menu;
        return;
    }
    let Some(payload) = app.settings.payload.clone() else { return }; // todavía cargando (GET /config)

    if app.settings.editing.is_some() {
        match code {
            KeyCode::Enter | KeyCode::Esc => {
                let buffer = app.settings.editing.take().unwrap();
                let svc = &payload.services[app.settings.selected_service];
                let rows = detail_rows(&svc.fields);
                if let DetailRow::Field(field_i) = rows[app.settings.selected_row] {
                    app.settings.edits.insert(svc.fields[field_i].env.clone(), buffer);
                }
            }
            KeyCode::Backspace => {
                if let Some(buffer) = &mut app.settings.editing {
                    buffer.pop();
                }
            }
            KeyCode::Char(c) => {
                if let Some(buffer) = &mut app.settings.editing {
                    buffer.push(c);
                }
            }
            _ => {}
        }
        return;
    }

    match code {
        KeyCode::Left => app.settings.focus = ConfigFocus::Services,
        KeyCode::Up => match app.settings.focus {
            ConfigFocus::Services => {
                app.settings.selected_service = app.settings.selected_service.saturating_sub(1);
                app.settings.selected_row = 0;
            }
            ConfigFocus::Detail => {
                let svc = &payload.services[app.settings.selected_service];
                let rows = detail_rows(&svc.fields);
                app.settings.selected_row = prev_row(&rows, app.settings.selected_row);
            }
        },
        KeyCode::Down => match app.settings.focus {
            ConfigFocus::Services => {
                app.settings.selected_service =
                    (app.settings.selected_service + 1).min(payload.services.len() - 1);
                app.settings.selected_row = 0;
            }
            ConfigFocus::Detail => {
                let svc = &payload.services[app.settings.selected_service];
                let rows = detail_rows(&svc.fields);
                app.settings.selected_row = next_row(&rows, app.settings.selected_row);
            }
        },
        KeyCode::Right | KeyCode::Enter if app.settings.focus == ConfigFocus::Services => {
            let svc = &payload.services[app.settings.selected_service];
            let rows = detail_rows(&svc.fields);
            app.settings.focus = ConfigFocus::Detail;
            app.settings.selected_row = first_row(&rows);
        }
        KeyCode::Char(' ') if app.settings.focus == ConfigFocus::Services => {
            let svc = &payload.services[app.settings.selected_service];
            if let (Some(orig), Some(env)) = (svc.enabled, &svc.enabled_env) {
                let effective = app.settings.edits.get(env).map(|v| v == "true").unwrap_or(orig);
                app.settings.edits.insert(env.clone(), (!effective).to_string());
            }
        }
        KeyCode::Enter | KeyCode::Char(' ') if app.settings.focus == ConfigFocus::Detail => {
            let svc = &payload.services[app.settings.selected_service];
            let rows = detail_rows(&svc.fields);
            if let DetailRow::Field(field_i) = rows[app.settings.selected_row] {
                let field = &svc.fields[field_i];
                if field.kind == "bool" {
                    let current = field_value(app, field) == "true";
                    app.settings.edits.insert(field.env.clone(), (!current).to_string());
                } else {
                    app.settings.editing = Some(field_value(app, field).to_string());
                }
            }
        }
        KeyCode::Char('s') if !app.settings.save_in_flight => {
            app.settings.save_in_flight = true;
            app.settings.status = None;
            tokio::spawn(crate::app::save_config(app.settings.edits.clone(), tx.clone()));
        }
        _ => {}
    }
}

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let Some(payload) = &app.settings.payload else {
        let loading = Paragraph::new(Line::from(Span::styled(
            " cargando configuración (GET /config)… ",
            Style::default().fg(app.colors.dim),
        )))
        .block(Block::default().borders(Borders::ALL).title(" ◈ CONFIGURAR "));
        f.render_widget(loading, area);
        return;
    };

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1)])
        .split(area);
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(35), Constraint::Percentage(65)])
        .split(rows[0]);

    draw_services(f, app, payload, cols[0]);
    draw_detail(f, app, payload, cols[1]);
    draw_status(f, app, rows[1]);
}

fn draw_services(f: &mut Frame, app: &App, payload: &ConfigPayload, area: ratatui::layout::Rect) {
    let items: Vec<ListItem> = payload
        .services
        .iter()
        .enumerate()
        .map(|(i, svc)| {
            let selected = i == app.settings.selected_service;
            let checkbox = match svc.enabled {
                None => "    ".to_string(),
                Some(orig) => {
                    let effective = svc
                        .enabled_env
                        .as_ref()
                        .and_then(|env| app.settings.edits.get(env))
                        .map(|v| v == "true")
                        .unwrap_or(orig);
                    format!("[{}] ", if effective { "x" } else { " " })
                }
            };
            let style = if selected && app.settings.focus == ConfigFocus::Services {
                Style::default().fg(app.colors.bg).bg(app.colors.accent).add_modifier(Modifier::BOLD)
            } else if selected {
                Style::default().fg(app.colors.accent)
            } else {
                Style::default().fg(app.colors.fg)
            };
            ListItem::new(format!("  {checkbox}{}", svc.display_name)).style(style)
        })
        .collect();
    let list = List::new(items).block(
        Block::default()
            .borders(Borders::ALL)
            .title(" ◈ SERVICIOS ")
            .border_style(Style::default().fg(app.colors.dim)),
    );
    f.render_widget(list, area);
}

fn draw_detail(f: &mut Frame, app: &App, payload: &ConfigPayload, area: ratatui::layout::Rect) {
    let svc = &payload.services[app.settings.selected_service];
    let rows = detail_rows(&svc.fields);
    let lines: Vec<Line> = rows
        .iter()
        .enumerate()
        .map(|(row_i, row)| match row {
            DetailRow::Header(label) => {
                Line::from(Span::styled(format!(" ── {label} ── "), Style::default().fg(app.colors.dim)))
            }
            DetailRow::Field(field_i) => {
                let field = &svc.fields[*field_i];
                let selected = app.settings.focus == ConfigFocus::Detail && row_i == app.settings.selected_row;
                let value = if selected && app.settings.editing.is_some() {
                    format!("{}▮", app.settings.editing.as_deref().unwrap_or(""))
                } else if field.kind == "bool" {
                    if field_value(app, field) == "true" { "[x]".to_string() } else { "[ ]".to_string() }
                } else {
                    field_value(app, field).to_string()
                };
                let color = if selected && app.settings.editing.is_some() {
                    app.colors.warn
                } else if selected {
                    app.colors.accent
                } else {
                    app.colors.fg
                };
                let marker = if selected { "▸ " } else { "  " };
                Line::from(Span::styled(format!("{marker}{}: {value}", field.attr), Style::default().fg(color)))
            }
        })
        .collect();
    let detail = Paragraph::new(lines).block(
        Block::default()
            .borders(Borders::ALL)
            .title(format!(" ◈ {} — PARÁMETROS ", svc.display_name))
            .border_style(Style::default().fg(app.colors.dim)),
    );
    f.render_widget(detail, area);
}

fn draw_status(f: &mut Frame, app: &App, area: ratatui::layout::Rect) {
    let line = if app.settings.save_in_flight {
        Line::from(Span::styled(" guardando (POST /config)… ", Style::default().fg(app.colors.warn)))
    } else if let Some(status) = &app.settings.status {
        match status {
            ConfigSaveStatus::Saved(msg) => {
                Line::from(Span::styled(format!(" {msg} "), Style::default().fg(app.colors.success)))
            }
            ConfigSaveStatus::Failed(msg) => {
                Line::from(Span::styled(format!(" {msg} "), Style::default().fg(app.colors.hot)))
            }
        }
    } else if app.settings.editing.is_some() {
        Line::from(Span::styled(
            " editando — Enter/Esc confirma ",
            Style::default().fg(app.colors.dim),
        ))
    } else {
        Line::from(Span::styled(
            " ←→ panel  ↑↓ mover  Enter/Espacio editar  s guardar  q/Esc volver ",
            Style::default().fg(app.colors.dim),
        ))
    };
    f.render_widget(Paragraph::new(line), area);
}
