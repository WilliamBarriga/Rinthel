//! Screen de cierre — puerto de `rinthel_tui/tui/screens/farewell.py`
//! (mockup construido en sesión 02, cableado en sesión 05 del port-map).
//!
//! Cableado (sesión 05, grillado con Tarkark 2026-09-16): los dos callers
//! de Python — `phase_runner.py:110` (tras un TERMINATE exitoso) y
//! `menu.py:183` (opción EXIT del menú) — están wireados acá vía
//! `App::farewell_next` (`app.rs`): `MenuAction::Quit` entra a esta screen
//! en vez de salir directo, y `App::finish_phase_sequence` hace lo mismo
//! tras un TERMINATE sin fallas. El atajo global `q` del spike (invención
//! pre-port, no existe en `farewell.py`) sigue matando la app incluso
//! durante estos 5s — decisión explícita de Tarkark, no se lo especial-casó
//! en el loop de `app.rs`. `farewell.py` tampoco bindea Esc, así que acá
//! tampoco hay guard de salida temprana: los 5s corren completos siempre.
//!
//! El `GlitchLabel` real (`rinthel_tui/tui/effects/flicker.py`) se retrofitea
//! en sesión 10 — el reveal vive en `App::farewell_message`
//! (`effects::flicker::GlitchReveal`, creado junto con `FarewellTimer` en
//! `App::begin_farewell`), acá solo se dibuja el texto que corresponda a
//! este instante.

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

pub fn draw(f: &mut Frame, fg: Color, text: &str) {
    let area = f.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1), Constraint::Min(0)])
        .split(area);
    let message =
        Paragraph::new(Line::from(Span::styled(text.to_string(), Style::default().fg(fg)))).alignment(Alignment::Center);
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
