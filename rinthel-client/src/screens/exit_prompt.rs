//! Prompt de confirmación al salir.
//!
//! Alcance: solo el camino `[N] SALIR` del menú (`MenuAction::Quit`); el
//! atajo global `q` sigue matando la app al instante desde cualquier
//! pantalla sin pasar por acá y sin tocar el daemon. Mecanismo de apagado:
//! invoca `./rinthel-boot.sh --stop` como subproceso
//! (`App::spawn_daemon_stop`, en `app.rs`) en vez de que el cliente lea el
//! pidfile y mande la señal él mismo, reusando la lógica ya existente ahí
//! (pid vivo, poll, pidfile stale). Ubicación: antes de la screen de
//! farewell, no la reemplaza — primero se decide si apagar, después corre
//! el mensaje de cierre de siempre.

use std::time::{Duration, Instant};

use ratatui::layout::{Alignment, Constraint, Direction, Layout};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

pub const EXIT_PROMPT_SECONDS: u64 = 5;

/// Mismo patrón que `farewell::FarewellTimer` — `App::run` lo consulta cada
/// vuelta del loop en vez de un callback; sin elección a tiempo, apaga todo
/// por default (a prueba de olvidos).
pub struct ExitPromptTimer {
    started: Instant,
}

impl ExitPromptTimer {
    pub fn start() -> Self {
        ExitPromptTimer { started: Instant::now() }
    }

    pub fn is_done(&self) -> bool {
        self.started.elapsed() >= Duration::from_secs(EXIT_PROMPT_SECONDS)
    }

    /// Countdown entero para la pantalla — techo, no piso (arranca en
    /// `EXIT_PROMPT_SECONDS`, no en `EXIT_PROMPT_SECONDS - 1`).
    pub fn remaining_secs(&self) -> u64 {
        let total = Duration::from_secs(EXIT_PROMPT_SECONDS);
        let elapsed = self.started.elapsed();
        if elapsed >= total {
            return 0;
        }
        ((total - elapsed).as_millis() as u64).div_ceil(1000)
    }
}

pub fn draw(f: &mut Frame, fg: Color, dim: Color, remaining: u64) {
    let area = f.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1), Constraint::Length(1), Constraint::Min(0)])
        .split(area);
    let question =
        Paragraph::new(Line::from(Span::styled("¿Apagar también el daemon? [Y/n]", Style::default().fg(fg))))
            .alignment(Alignment::Center);
    f.render_widget(question, rows[1]);
    let hint = Paragraph::new(Line::from(Span::styled(
        format!("sin elegir, apaga en {remaining}s — q sale sin apagar el daemon"),
        Style::default().fg(dim),
    )))
    .alignment(Alignment::Center);
    f.render_widget(hint, rows[2]);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn not_done_immediately() {
        let timer = ExitPromptTimer::start();
        assert!(!timer.is_done());
        assert_eq!(timer.remaining_secs(), EXIT_PROMPT_SECONDS);
    }

    #[test]
    fn done_after_deadline() {
        let timer = ExitPromptTimer { started: Instant::now() - Duration::from_secs(EXIT_PROMPT_SECONDS + 1) };
        assert!(timer.is_done());
        assert_eq!(timer.remaining_secs(), 0);
    }
}
