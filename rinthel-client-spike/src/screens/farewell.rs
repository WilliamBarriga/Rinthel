//! Screen de cierre — puerto de `rinthel_tui/tui/screens/farewell.py`
//! (sesión 02 del port-map). Mockup sin cablear a propósito (grillado con
//! Tarkark 2026-09-16): sesión 05 (`phase_runner`) decide cómo se dispara
//! y construye — por eso este módulo no toca `ScreenId`/`MENU_ENTRIES` ni
//! `app.rs`.
//!
//! El `GlitchLabel` real (`rinthel_tui/tui/effects/flicker.py`) queda
//! stubbeado — texto directo, sin animación — confirmado en el ticket de
//! esta sesión; se retrofitea en sesión 10.
//!
//! NOTA PARA SESIÓN 05: Python tiene un segundo caller de `FarewellScreen`
//! además de `phase_runner.py:110` — `menu.py:183`, la opción "exit" del
//! menú (hoy `MenuAction::Quit` acá, que sale sin pasar por nada). Revisar
//! ahí si corresponde cablearlo también, y qué hace el atajo global `q`
//! del spike (no existe en Python) mientras corre este timer — anotado
//! como pendiente en el port-map, no decidido en esta sesión.

use std::time::{Duration, Instant};

use ratatui::layout::{Alignment, Constraint, Direction, Layout};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

pub const FAREWELL_SECONDS: u64 = 5;
pub const MESSAGE: &str = "RINTHEL.AI — SESSION CLOSED";

/// Reemplaza `set_timer(FAREWELL_SECONDS, self._finish)` + `dismiss()` de
/// `farewell.py`: quien cablee esta screen guarda un `FarewellTimer` al
/// entrar y consulta `is_done()` en cada tick de su loop, en vez de un
/// callback awaiteable (el modelo de `app.rs` no tiene stack de screens).
pub struct FarewellTimer {
    started: Instant,
}

impl FarewellTimer {
    pub fn start() -> Self {
        FarewellTimer { started: Instant::now() }
    }

    pub fn is_done(&self) -> bool {
        self.started.elapsed() >= Duration::from_secs(FAREWELL_SECONDS)
    }
}

pub fn draw(f: &mut Frame, fg: Color) {
    let area = f.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1), Constraint::Min(0)])
        .split(area);
    let message = Paragraph::new(Line::from(Span::styled(MESSAGE, Style::default().fg(fg))))
        .alignment(Alignment::Center);
    f.render_widget(message, rows[1]);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn not_done_immediately() {
        let timer = FarewellTimer::start();
        assert!(!timer.is_done());
    }

    #[test]
    fn done_after_deadline() {
        let timer = FarewellTimer { started: Instant::now() - Duration::from_secs(FAREWELL_SECONDS + 1) };
        assert!(timer.is_done());
    }
}
