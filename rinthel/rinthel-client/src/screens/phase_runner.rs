//! Screen genérica de checklist + log para BOOT/TERMINATE/RELOAD/INSTALL —
//! las 4 comparten `ScreenId::PhaseRunner` (no una screen por comando)
//! porque con la orquestación completa del lado daemon no queda ningún
//! comportamiento propio por comando del lado cliente. La rotación de un
//! secreto (`POST /secrets/rotate`, desde Settings) corre acá también.
//!
//! El estado (`phase_rows`/`phase_log`) vive en `App`, no en un struct de
//! screen propio (`command_in_flight` +
//! `last_command_result`), porque `app.rs` no tiene un stack de screens.
//! `app::finish_phase_sequence` llena `phase_log` con el cierre (mensaje/
//! banner de cierre, o "secuencia cortada") cuando llega la respuesta del
//! POST — acá solo se dibuja.

use crossterm::event::KeyCode;
use std::collections::VecDeque;
use std::time::Instant;

use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use ratatui::Frame;

use crate::app::App;
use crate::widgets::checklist;

/// Local observation times: no daemon clock synchronization is needed.
#[derive(Default)]
pub struct Progress {
    started: Option<Instant>,
    finished: Option<Instant>,
    activity: Option<Instant>,
    batch: String,
    step: String,
    expanded: bool,
    /// Other lifecycle commands retain their checklist beside the full log.
    keep_checklist: bool,
    scroll_x: u16,
    /// A phase failed: the log opens in full and wraps, so the error is readable.
    failed: bool,
}

impl Progress {
    pub fn start(&mut self, now: Instant, reload: bool) {
        *self = Self {
            started: Some(now),
            batch: if reload { "shutdown".into() } else { String::new() },
            expanded: !reload,
            keep_checklist: !reload,
            ..Self::default()
        };
    }

    pub fn observe(&mut self, now: Instant) {
        self.started.get_or_insert(now);
        self.activity = Some(now);
    }

    pub fn batch(&mut self, batch: String, now: Instant) {
        self.observe(now);
        self.batch = batch;
        self.step.clear();
    }

    pub fn step(&mut self, label: String, status: &str, now: Instant) {
        self.observe(now);
        self.step = format!("{label} ({status})");
    }

    /// Auto-expand on failure; Tab can still collapse it, a new error re-expands.
    pub fn fail(&mut self) {
        self.failed = true;
        self.expanded = true;
        self.scroll_x = 0;
    }

    pub fn finish(&mut self, now: Instant) {
        self.finished = Some(now);
    }

    pub fn handle_key(&mut self, key: KeyCode) -> bool {
        match key {
            KeyCode::Tab => self.expanded = !self.expanded,
            KeyCode::Left => self.scroll_x = self.scroll_x.saturating_sub(8),
            KeyCode::Right => self.scroll_x = self.scroll_x.saturating_add(8),
            KeyCode::Home => self.scroll_x = 0,
            _ => return false,
        }
        true
    }

    fn summary(&self, now: Instant) -> Vec<Line<'static>> {
        let end = self.finished.unwrap_or(now);
        let elapsed = self
            .started
            .map_or(0, |start| end.saturating_duration_since(start).as_secs());
        let age = self.activity.map_or("sin eventos".into(), |last| {
            format!("hace {} s", now.saturating_duration_since(last).as_secs())
        });
        vec![
            Line::from(format!(
                "Fase: {} · Paso: {}",
                if self.batch.is_empty() {
                    "preparación"
                } else {
                    &self.batch
                },
                if self.step.is_empty() {
                    "esperando progreso"
                } else {
                    &self.step
                }
            )),
            Line::from(format!("Transcurrido: {elapsed} s · Última actividad: {age}")),
        ]
    }
}

fn log_lines<'a>(log: &'a VecDeque<(String, String)>, colors: &crate::app::Colors) -> Vec<Line<'a>> {
    log.iter()
        .flat_map(|(kind, msg)| msg.lines().map(move |line| (kind, line)))
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

/// Rows a line takes under the same `Wrap { trim: false }` the log is drawn with: ratatui's own
/// count (feature `unstable-rendered-line-info`), so the estimate cannot drift from the render.
fn wrapped_rows(text: &str, width: usize) -> usize {
    let width = width.clamp(1, u16::MAX as usize) as u16;
    Paragraph::new(text.to_owned()).wrap(Wrap { trim: false }).line_count(width).max(1)
}

pub fn draw(f: &mut Frame, app: &App) {
    draw_at(f, app, Instant::now());
}

pub fn draw_at(f: &mut Frame, app: &App, now: Instant) {
    let area = f.area();
    let expanded = app.phase_progress.expanded;
    let checklist_height = if expanded && !app.phase_progress.keep_checklist {
        0
    } else {
        (app.phase_rows.len() as u16 + 2).min(area.height.saturating_sub(8))
    };
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2),
            Constraint::Length(checklist_height),
            Constraint::Min(0),
            Constraint::Length(1),
        ])
        .split(area);
    f.render_widget(Paragraph::new(app.phase_progress.summary(now)), rows[0]);
    if checklist_height > 0 {
        checklist::draw(f, rows[1], &app.phase_rows, &app.colors);
    }
    let height = rows[2].height.saturating_sub(2) as usize;
    let lines = log_lines(&app.phase_log, &app.colors);
    let wrap = app.phase_progress.failed;
    let inner_width = rows[2].width.saturating_sub(2) as usize;
    let visible = if expanded { height } else { height.min(1) };
    let mut tail: Vec<Line> = Vec::new();
    let mut used = 0;
    for line in lines.into_iter().rev() {
        let n = if wrap { wrapped_rows(&line.to_string(), inner_width) } else { 1 };
        if !tail.is_empty() && used + n > visible {
            break;
        }
        used += n;
        tail.push(line);
        if used >= visible {
            break;
        }
    }
    tail.reverse();
    let mut log = Paragraph::new(tail)
        .block(Block::default().borders(Borders::ALL).title(app.phase_title));
    log = if wrap {
        // ratatui ignores x scroll under Wrap: ←→/Home are no-ops while a failure is shown.
        log.wrap(Wrap { trim: false }).scroll((used.saturating_sub(visible) as u16, 0))
    } else {
        log.scroll((0, app.phase_progress.scroll_x))
    };
    f.render_widget(log, rows[2]);
    let hint = Paragraph::new(Line::from(Span::styled(
        "Tab: detalle · ←→: desplazar (sin error) · Home: inicio · Ctrl+C cancelar · Esc volver al terminar",
        Style::default().fg(app.colors.dim),
    )));
    f.render_widget(hint, rows[3]);
}

/// "No hay POST /boot/terminate/reload/install en vuelo".
pub fn done(app: &App) -> bool {
    app.command_in_flight.is_none()
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::{backend::TestBackend, Terminal};

    /// Draws `text` in a box exactly `wrapped_rows` tall and returns the screen text.
    fn rendered(text: &str, width: usize) -> String {
        let rows = wrapped_rows(text, width);
        let mut term = Terminal::new(TestBackend::new(width as u16, rows as u16)).unwrap();
        term.draw(|f| {
            f.render_widget(Paragraph::new(text.to_owned()).wrap(Wrap { trim: false }), f.area());
        })
        .unwrap();
        let buf = term.backend().buffer().clone();
        (0..buf.area.height)
            .flat_map(|y| (0..buf.area.width).map(move |x| (x, y)))
            .map(|(x, y)| buf[(x, y)].symbol().to_owned())
            .collect()
    }

    #[test]
    fn the_end_of_a_long_error_is_never_clipped_at_any_width() {
        let texts = [
            "  ✖ llama-server: la fase wait-ready falló: no respondió en 90 s; revise el log FINALMARK",
            "  ✖ /home/admin/rinthel/data/models/una/ruta/larga/sin/espacios/que/no/cabe/en/ninguna/linea/FINALMARK",
            "x FINALMARK",
            "FINALMARK",
        ];
        for text in texts {
            for width in [1usize, 2, 7, 10, 20, 33, 40, 80, 120] {
                let screen = rendered(text, width);
                assert!(screen.trim_end().ends_with('K'), "width {width}: end clipped for {text:?}: {screen:?}");
            }
        }
    }

    #[test]
    fn an_empty_line_still_takes_one_row() {
        assert_eq!(wrapped_rows("", 10), 1);
    }
}
