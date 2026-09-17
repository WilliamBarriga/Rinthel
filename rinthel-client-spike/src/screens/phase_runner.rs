//! Screen genérica de checklist + log para BOOT/TERMINATE/RELOAD — puerto
//! de `PhaseSequenceScreen`/`PhaseRunnerScreen`
//! (`rinthel_tui/tui/screens/phase_runner.py`, sesión 05 del port-map).
//!
//! RELOAD (sesión 06) reusa esta screen tal cual en vez de tener la suya
//! propia (`ScreenId::PhaseRunner`, no `ScreenId::Reload`): con las 3
//! tandas orquestadas del lado daemon (`POST /reload`) y las transiciones
//! entre tandas stubbeadas a nada, no queda ningún comportamiento propio de
//! Reload del lado cliente — grillado con Tarkark antes de proceder.
//!
//! El estado (`phase_rows`/`phase_log`) vive en `App`, no en un struct de
//! screen propio — mismo patrón que `capture.rs` (`command_in_flight` +
//! `last_command_result`), porque `app.rs` no tiene un stack de screens al
//! estilo Textual. `app::finish_phase_sequence` llena `phase_log` con el
//! cierre (mensaje/banner de cierre, o "secuencia cortada") cuando llega la
//! respuesta del POST — acá solo se dibuja.
//!
//! Los efectos de cierre (`ChromaticAberrationEffect`/`AfterimageEffect`, y
//! para reload las 3 transiciones entre tandas) quedan stubbeados: el
//! banner es una línea más del log, sin transición — confirmado en el
//! ticket, retrofit real en sesión 10.

use std::collections::VecDeque;

use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;

use crate::app::App;
use crate::widgets::checklist;

fn log_lines<'a>(log: &'a VecDeque<(String, String)>, colors: &crate::app::Colors) -> Vec<Line<'a>> {
    log.iter()
        .map(|(kind, msg)| {
            let (icon, color) = match kind.as_str() {
                "success" => ("●", colors.success),
                "warn" => ("▲", colors.warn),
                "error" => ("✖", colors.hot),
                _ => ("·", colors.dim),
            };
            Line::from(Span::styled(format!("  {icon} {msg}"), Style::default().fg(color)))
        })
        .collect()
}

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    // `.max(3)` en el tope evita un panic de `clamp` (mín > máx) en una
    // terminal tan chica que `area.height.saturating_sub(4)` caiga por
    // debajo del piso de 3.
    let checklist_height = (app.phase_rows.len() as u16 + 2).clamp(3, area.height.saturating_sub(4).max(3));
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(checklist_height), Constraint::Min(0), Constraint::Length(1)])
        .split(area);

    checklist::draw(f, rows[0], &app.phase_rows, &app.colors);

    let log = Paragraph::new(log_lines(&app.phase_log, &app.colors))
        .block(Block::default().borders(Borders::ALL).title(app.phase_title));
    f.render_widget(log, rows[1]);

    let hint = Paragraph::new(Line::from(Span::styled(
        "Ctrl+C para cancelar · Esc para volver al terminar",
        Style::default().fg(app.colors.dim),
    )));
    f.render_widget(hint, rows[2]);
}

/// `action_dismiss_if_done` de `phase_runner.py` — acá es "no hay POST
/// /boot ni /terminate en vuelo", mismo truco que `screens::capture::done`.
pub fn done(app: &App) -> bool {
    app.command_in_flight.is_none()
}
