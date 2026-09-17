//! Screen de `[N] CONFIGURAR` — puerto de
//! `rinthel_tui/tui/screens/settings.py` (sesión 09 del port-map).
//!
//! Grillado con Tarkark 2026-09-16: el daemon pasa a ser dueño de toda la
//! config (amendment de docs/adr/0001, ver `protocol::ConfigPayload`) — este
//! módulo no conoce los campos de `llama`/`understory`/`pithagoras`/`moe`
//! por su nombre, los recorre genéricamente igual que hacía
//! `settings.py` con `config._ENTRIES`. `install` queda fuera de esta
//! screen a propósito (decisión de esa sesión) aunque el `GET /config`
//! del daemon lo traiga igual — acá simplemente no se itera.
//!
//! Fix de nombre de la misma sesión: el campo que armaba `-fit`
//! (`services.py::_llama_argv`) se llamaba `flash_inference` y ahora es
//! `fit_to_memory` — ya viene corregido desde el daemon, este módulo no
//! sabe ni le importa el nombre viejo.
//!
//! Agrupación por función técnica (Sampling/Cache/Cómputo/Speculative/
//! General) es una decisión del **cliente**, no del daemon: `ConfigField.group`
//! viaja como string plano y NO llega en orden contiguo por grupo (ver
//! `config.py::LLAMA_FIELDS` — `context_window` es "general" entre dos
//! campos "compute", por ejemplo), así que `detail_rows` bucketea por grupo
//! en vez de solo detectar transiciones. Sub-configs con `group == ""`
//! (`understory`/`pithagoras`/`moe`, pocos campos) caen a una lista plana
//! sin headers.

use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph};
use ratatui::Frame;

use crate::app::{App, ConfigFocus};
use crate::protocol::ConfigField;

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

/// Valor efectivo de un campo — el edit en curso (`app.config_edits`) si lo
/// tocaste esta sesión, si no el que trajo el `GET /config`. Mismo criterio
/// que `self._edits.get(f.env, stringify(...))` en `settings.py`.
pub fn field_value<'a>(app: &'a App, field: &'a ConfigField) -> &'a str {
    app.config_edits.get(&field.env).map(String::as_str).unwrap_or(&field.value)
}

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let Some(payload) = &app.config else {
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

fn draw_services(f: &mut Frame, app: &App, payload: &crate::protocol::ConfigPayload, area: ratatui::layout::Rect) {
    let items: Vec<ListItem> = payload
        .services
        .iter()
        .enumerate()
        .map(|(i, svc)| {
            let selected = i == app.config_selected_service;
            let checkbox = match svc.enabled {
                None => "    ".to_string(),
                Some(orig) => {
                    let effective = svc
                        .enabled_env
                        .as_ref()
                        .and_then(|env| app.config_edits.get(env))
                        .map(|v| v == "true")
                        .unwrap_or(orig);
                    format!("[{}] ", if effective { "x" } else { " " })
                }
            };
            let style = if selected && app.config_focus == ConfigFocus::Services {
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

fn draw_detail(f: &mut Frame, app: &App, payload: &crate::protocol::ConfigPayload, area: ratatui::layout::Rect) {
    let svc = &payload.services[app.config_selected_service];
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
                let selected = app.config_focus == ConfigFocus::Detail && row_i == app.config_selected_row;
                let value = if selected && app.config_editing.is_some() {
                    format!("{}▮", app.config_editing.as_deref().unwrap_or(""))
                } else if field.kind == "bool" {
                    if field_value(app, field) == "true" { "[x]".to_string() } else { "[ ]".to_string() }
                } else {
                    field_value(app, field).to_string()
                };
                let color = if selected && app.config_editing.is_some() {
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
    let line = if app.config_save_in_flight {
        Line::from(Span::styled(" guardando (POST /config)… ", Style::default().fg(app.colors.warn)))
    } else if let Some(status) = &app.config_status {
        match status {
            crate::app::ConfigSaveStatus::Saved(msg) => {
                Line::from(Span::styled(format!(" {msg} "), Style::default().fg(app.colors.success)))
            }
            crate::app::ConfigSaveStatus::Failed(msg) => {
                Line::from(Span::styled(format!(" {msg} "), Style::default().fg(app.colors.hot)))
            }
        }
    } else if app.config_editing.is_some() {
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
