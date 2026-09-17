//! Registro de screens: un enum de identificadores + una lista de registro,
//! para que agregar una screen/opción de menú no toque el loop principal en
//! `app.rs`.

pub mod capture;
pub mod exit_prompt;
pub mod farewell;
pub mod logs;
pub mod menu;
pub mod monitor;
pub mod phase_runner;
pub mod settings;

use crossterm::event::KeyCode;
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::Frame;
use tokio::sync::mpsc;

use crate::app::{App, AppEvent};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScreenId {
    Menu,
    Monitor,
    Logs,
    Capture,
    /// Checklist + log en vivo de BOOT/TERMINATE/RELOAD/INSTALL.
    PhaseRunner,
    /// "¿Apagar también el daemon?" — antes de `Farewell` en el camino
    /// `[N] SALIR` (`MenuAction::Quit`).
    ExitPrompt,
    /// Cierre de sesión.
    Farewell,
    /// `[N] CONFIGURAR`.
    Settings,
}

#[derive(Clone, Copy)]
pub enum MenuAction {
    Navigate(ScreenId),
    Boot,
    Terminate,
    /// Reusa `ScreenId::PhaseRunner` tal cual, mismo mecanismo bloqueante
    /// que Boot/Terminate contra `POST /reload` (las 3 tandas de
    /// `specs.reload_units` corren del lado daemon; el cliente no distingue
    /// reload de un boot/terminate más largo).
    Reload,
    /// Distinta de `Navigate`: entrar a Capture dispara `POST /capture` de
    /// una — no es solo cambiar de screen.
    Capture,
    /// Reusa `ScreenId::PhaseRunner` tal cual, mismo argumento que `Reload`:
    /// con `specs.install_units` orquestando todo del lado daemon, no queda
    /// comportamiento propio para una screen de Install en el cliente.
    Install,
    /// Distinta de `Navigate`: entrar dispara `GET /config` de una, mismo
    /// argumento que `Capture` con `POST /capture`.
    Settings,
    Quit,
}

#[derive(Clone, Copy)]
pub struct MenuEntry {
    pub label: &'static str,
    pub action: MenuAction,
}

/// Un ítem del menú — o una entrada accionable, o un separador puramente
/// visual. Separar esto en un enum (en vez de, por ejemplo, un flag
/// `disabled` en `MenuEntry` o índices de divisor hardcodeados) es lo que
/// permite agregar/sacar/mover entradas y separadores en `MENU_ENTRIES` sin
/// tocar la navegación: `Up`/`Down` (`next_selectable`/`prev_selectable`,
/// más abajo) saltan `Divider` solos, así que ningún índice queda
/// hardcodeado en otro lado.
#[derive(Clone, Copy)]
pub enum MenuItem {
    Entry(MenuEntry),
    Divider,
}

impl MenuItem {
    pub fn as_entry(&self) -> Option<&MenuEntry> {
        match self {
            MenuItem::Entry(e) => Some(e),
            MenuItem::Divider => None,
        }
    }
}

// Sin divisores todavía (pulido visual pendiente): la estructura ya los
// soporta, agregarlos es sumar `MenuItem::Divider` donde corresponda.
pub const MENU_ENTRIES: &[MenuItem] = &[
    MenuItem::Entry(MenuEntry { label: "MONITOR", action: MenuAction::Navigate(ScreenId::Monitor) }),
    MenuItem::Entry(MenuEntry { label: "BOOT", action: MenuAction::Boot }),
    MenuItem::Entry(MenuEntry { label: "RELOAD", action: MenuAction::Reload }),
    MenuItem::Entry(MenuEntry { label: "TERMINATE", action: MenuAction::Terminate }),
    MenuItem::Entry(MenuEntry { label: "CONFIGURAR", action: MenuAction::Settings }),
    MenuItem::Entry(MenuEntry { label: "CAPTURE", action: MenuAction::Capture }),
    MenuItem::Entry(MenuEntry { label: "LOGS", action: MenuAction::Navigate(ScreenId::Logs) }),
    MenuItem::Entry(MenuEntry { label: "INSTALL", action: MenuAction::Install }),
    MenuItem::Entry(MenuEntry { label: "SALIR", action: MenuAction::Quit }),
];

/// Primer índice seleccionable de `MENU_ENTRIES` — usado para saltar
/// `Divider` sin asumir que el índice 0 siempre es una `Entry`.
pub fn first_selectable() -> usize {
    MENU_ENTRIES
        .iter()
        .position(|item| matches!(item, MenuItem::Entry(_)))
        .expect("MENU_ENTRIES sin ninguna entrada seleccionable")
}

/// Próxima `Entry` seleccionable a partir de (sin incluir) `from` — se queda
/// en `from` si ya es la última (mismo comportamiento de "tope" que el
/// `.min(...)` que reemplaza).
pub fn next_selectable(from: usize) -> usize {
    MENU_ENTRIES
        .iter()
        .enumerate()
        .skip(from + 1)
        .find(|(_, item)| matches!(item, MenuItem::Entry(_)))
        .map(|(i, _)| i)
        .unwrap_or(from)
}

/// Entry seleccionable anterior a `from` — se queda en `from` si ya es la
/// primera.
pub fn prev_selectable(from: usize) -> usize {
    MENU_ENTRIES[..from]
        .iter()
        .enumerate()
        .rev()
        .find(|(_, item)| matches!(item, MenuItem::Entry(_)))
        .map(|(i, _)| i)
        .unwrap_or(from)
}

/// Espeja `draw`: le da a cada screen un lugar dedicado para su propio
/// manejo de teclado, en vez de que `App::run()` sea el único que conoce las
/// teclas de todas — mismo principio que recomienda la guía de "Component
/// Architecture" de ratatui (co-locar `handle_events`/`update`/`render` a
/// nivel de componente), sin adoptar el trait `Component` completo.
///
/// Devuelve `true` si la screen consumió la tecla — `App::run()` solo cae al
/// match genérico (Esc/q compartidos, scroll de log, etc.) si devuelve
/// `false`. Hoy solo Settings tiene sub-estado propio que lo justifique
/// (`settings::handle_key`); el resto sigue resuelto inline en `App::run()`
/// hasta que a alguna le haga falta lo mismo.
pub fn handle_key(id: ScreenId, app: &mut App, code: KeyCode, tx: &mpsc::UnboundedSender<AppEvent>) -> bool {
    match id {
        ScreenId::Settings => {
            settings::handle_key(app, code, tx);
            true
        }
        _ => false,
    }
}

pub fn draw(id: ScreenId, f: &mut Frame, app: &App) {
    match id {
        ScreenId::Menu => menu::draw(f, app),
        ScreenId::Monitor => monitor::draw(f, app),
        ScreenId::Logs => logs::draw(f, app),
        ScreenId::Capture => capture::draw(f, app),
        ScreenId::PhaseRunner => phase_runner::draw(f, app),
        ScreenId::ExitPrompt => {
            let remaining = app.exit_prompt_timer.as_ref().map(|t| t.remaining_secs()).unwrap_or(0);
            exit_prompt::draw(f, app.colors.fg, app.colors.dim, remaining);
        }
        ScreenId::Farewell => {
            let now = std::time::Instant::now();
            let text = app.farewell_message.as_ref().map(|g| g.text(now)).unwrap_or(farewell::MESSAGE);
            farewell::draw(f, app.colors.fg, text);
        }
        ScreenId::Settings => settings::draw(f, app),
    }
}

/// Feedback de boot/terminate — antes solo la pintaba `draw_monitor`, así
/// que dispararlos desde el menú (Enter sobre BOOT/TERMINATE) no mostraba
/// nada hasta cambiar de pantalla. Compartido entre `menu` y `monitor`.
fn status_line(app: &App) -> Line<'static> {
    if let Some(name) = app.command_in_flight {
        Line::from(Span::styled(
            format!(" {name}... (bloqueante, protocolo POST) "),
            Style::default().fg(app.colors.warn),
        ))
    } else if let Some(err) = &app.last_command_error {
        Line::from(Span::styled(format!(" {err} "), Style::default().fg(app.colors.hot)))
    } else if let Some((name, result)) = &app.last_command_result {
        let ok_count = result.results.iter().filter(|r| r.ok).count();
        match result.results.iter().find(|r| !r.ok) {
            Some(failed) => Line::from(Span::styled(
                format!(
                    " {name}: {ok_count}/{} ok — {} falló: {} ",
                    result.results.len(),
                    failed.service,
                    failed.message
                ),
                Style::default().fg(app.colors.hot),
            )),
            None => Line::from(Span::styled(
                format!(" {name}: {ok_count}/{} ok ", result.results.len()),
                Style::default().fg(app.colors.success),
            )),
        }
    } else {
        let hint = match app.screen {
            ScreenId::Menu => " ↑↓=mover  Enter=elegir  q=salir ",
            ScreenId::Monitor => " Esc=menu  q=salir  ←→=scroll log ",
            ScreenId::Logs => " q/Esc=volver  ←→=scroll  Home/End ",
            ScreenId::Capture => " Esc=volver (al terminar) ",
            ScreenId::PhaseRunner => " Esc=volver (al terminar) ",
            ScreenId::ExitPrompt => " Y/n=elegir  q=salir sin apagar ",
            ScreenId::Farewell => " cerrando sesión… ",
            // Nunca se pinta en la práctica — Settings tiene su propia
            // línea de estado (`settings::draw_status`, save en curso/error
            // de validación en vez de CommandResult); solo acá para que
            // este match siga siendo exhaustivo sobre ScreenId.
            ScreenId::Settings => " q/Esc=volver ",
        };
        Line::from(Span::styled(hint, Style::default().fg(app.colors.dim)))
    }
}
