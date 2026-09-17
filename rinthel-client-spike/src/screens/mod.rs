//! Registro de screens: reemplaza el `match app.menu_selected { 0 => ... }`
//! hardcodeado y el array fijo de labels que vivían en `main.rs` (ver
//! sesión 00 del port-map) por un enum de identificadores + una lista de
//! registro, para que agregar una screen/opción de menú no toque el loop
//! principal en `app.rs`.

pub mod capture;
pub mod farewell;
pub mod logs;
pub mod menu;
pub mod monitor;

use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::Frame;

use crate::app::App;

// `farewell` (sesión 02) no tiene variante acá a propósito — es un mockup
// sin cablear, ver el doc-comment de `farewell.rs` para el porqué y lo
// pendiente de sesión 05.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScreenId {
    Menu,
    Monitor,
    Logs,
    Capture,
}

#[derive(Clone, Copy)]
pub enum MenuAction {
    Navigate(ScreenId),
    Boot,
    Terminate,
    /// Distinta de `Navigate`: entrar a Capture dispara `POST /capture` de
    /// una, como `on_mount` en `capture.py` — no es solo cambiar de screen.
    Capture,
    Quit,
}

#[derive(Clone, Copy)]
pub struct MenuEntry {
    pub label: &'static str,
    pub action: MenuAction,
}

pub const MENU_ENTRIES: &[MenuEntry] = &[
    MenuEntry { label: "MONITOR", action: MenuAction::Navigate(ScreenId::Monitor) },
    MenuEntry { label: "LOGS", action: MenuAction::Navigate(ScreenId::Logs) },
    MenuEntry { label: "BOOT", action: MenuAction::Boot },
    MenuEntry { label: "TERMINATE", action: MenuAction::Terminate },
    MenuEntry { label: "CAPTURE", action: MenuAction::Capture },
    MenuEntry { label: "SALIR", action: MenuAction::Quit },
];

pub fn draw(id: ScreenId, f: &mut Frame, app: &App) {
    match id {
        ScreenId::Menu => menu::draw(f, app),
        ScreenId::Monitor => monitor::draw(f, app),
        ScreenId::Logs => logs::draw(f, app),
        ScreenId::Capture => capture::draw(f, app),
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
            ScreenId::Monitor => " b=boot  t=terminate  Esc=menu  q=salir ",
            ScreenId::Logs => " q/Esc=volver ",
            ScreenId::Capture => " Esc=volver (al terminar) ",
        };
        Line::from(Span::styled(hint, Style::default().fg(app.colors.dim)))
    }
}
