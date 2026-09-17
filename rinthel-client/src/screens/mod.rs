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
pub mod phase_runner;
pub mod settings;

use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::Frame;

use crate::app::App;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScreenId {
    Menu,
    Monitor,
    Logs,
    Capture,
    /// Checklist + log de BOOT/TERMINATE — sesión 05 del port-map.
    PhaseRunner,
    /// Cierre de sesión (mockup sesión 02, cableado sesión 05).
    Farewell,
    /// `[N] CONFIGURAR` — sesión 09 del port-map.
    Settings,
}

#[derive(Clone, Copy)]
pub enum MenuAction {
    Navigate(ScreenId),
    Boot,
    Terminate,
    /// Puerto de RELOAD (sesión 06 del port-map) — reusa `ScreenId::PhaseRunner`
    /// tal cual, mismo mecanismo bloqueante que Boot/Terminate contra
    /// `POST /reload` (las 3 tandas de `specs.reload_units` corren del lado
    /// daemon; el cliente no distingue reload de un boot/terminate más largo).
    Reload,
    /// Distinta de `Navigate`: entrar a Capture dispara `POST /capture` de
    /// una, como `on_mount` en `capture.py` — no es solo cambiar de screen.
    Capture,
    /// Puerto de `[0] INSTALL` (sesión 07 del port-map) — reusa
    /// `ScreenId::PhaseRunner` tal cual, mismo argumento que `Reload`: con
    /// `specs.install_units` orquestando todo del lado daemon, no queda
    /// comportamiento propio para una screen de Install en el cliente.
    Install,
    /// Puerto de `[N] CONFIGURAR` (sesión 09 del port-map) — distinta de
    /// `Navigate`: entrar dispara `GET /config` de una, mismo argumento que
    /// `Capture` con `POST /capture`.
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
/// `disabled` en `MenuEntry` o índices de divisor hardcodeados como
/// `menu.py::_DIVIDER_INDEX_1/2/3`) es lo que permite agregar/sacar/mover
/// entradas y separadores en `MENU_ENTRIES` sin tocar la navegación: `Up`/
/// `Down` (`next_selectable`/`prev_selectable`, más abajo) saltan
/// `Divider` solos, así que ningún índice queda hardcodeado en otro lado.
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

// Orden fijado en la sesión 07 del port-map (grillado con Tarkark) para lo
// que hoy existía del lado Rust; `CONFIGURAR` (sesión 09) entra acá, entre
// TERMINATE y CAPTURE, tal cual esa sesión ya lo había reservado. Sin
// divisores todavía (eso sigue siendo pulido visual de sesión 10): la
// estructura ya los soporta, agregarlos es sumar `MenuItem::Divider` donde
// corresponda.
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

pub fn draw(id: ScreenId, f: &mut Frame, app: &App) {
    match id {
        ScreenId::Menu => menu::draw(f, app),
        ScreenId::Monitor => monitor::draw(f, app),
        ScreenId::Logs => logs::draw(f, app),
        ScreenId::Capture => capture::draw(f, app),
        ScreenId::PhaseRunner => phase_runner::draw(f, app),
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
            ScreenId::Monitor => " Esc=menu  q=salir ",
            ScreenId::Logs => " q/Esc=volver ",
            ScreenId::Capture => " Esc=volver (al terminar) ",
            ScreenId::PhaseRunner => " Esc=volver (al terminar) ",
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
