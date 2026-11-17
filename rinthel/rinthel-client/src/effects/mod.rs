//! Los 8 efectos visuales que Rinthel usa: `GlitchLabel`/`RotatingTagline`
//! (texto inline, no bloqueantes) en [`flicker`]/[`tagline`], y los 6
//! `TransitionEffect` (modales bloqueantes) en [`transitions`], unificados
//! acá bajo [`ActiveEffect`].
//!
//! Cada `TransitionEffect` se dibuja SOBRE la screen de siempre y solo pinta
//! las celdas que toca (nunca un clear completo): `App::run` dibuja la
//! screen de siempre y, si `active_effect` está `Some`, superpone su grilla
//! — [`GridWidget`] deja intactas las celdas que la grilla no tocó (espacio
//! + sin estilo) en vez de pisarlas.
//!
//! Cada efecto de transición se guía por reloj de pared (`Instant`): no hay
//! corutinas acá, `App::run` es un loop de polling. Cada struct guarda
//! cuándo le toca el próximo cambio de frame (`next_at`) y lo recalcula en
//! `advance()`, empujado por el tick del loop en vez de un sleep asíncrono.

pub mod flicker;
pub mod tagline;
pub mod transitions;

use std::time::Instant;

use rand::Rng;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::style::Style;
use ratatui::widgets::Widget;

use crate::app::Colors;

pub type Cell = (char, Option<Style>);
pub type Grid = Vec<Vec<Cell>>;

pub fn blank_grid(width: usize, height: usize) -> Grid {
    vec![vec![(' ', None); width]; height]
}

/// Pinta encima de lo que ya dibujó la screen de abajo, sin tocar las
/// celdas que la grilla dejó en blanco (`' '`, sin estilo).
pub struct GridWidget<'a>(pub &'a Grid);

impl Widget for GridWidget<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        for (y, row) in self.0.iter().enumerate() {
            let Some(py) = area.y.checked_add(y as u16) else { break };
            if py >= area.y + area.height {
                break;
            }
            for (x, (ch, style)) in row.iter().enumerate() {
                if *ch == ' ' && style.is_none() {
                    continue; // sin tocar — deja pasar lo que ya había
                }
                let Some(px) = area.x.checked_add(x as u16) else { break };
                if px >= area.x + area.width {
                    break;
                }
                let cell = buf.cell_mut((px, py)).expect("dentro de area, checkeado arriba");
                cell.set_char(*ch);
                if let Some(style) = style {
                    cell.set_style(*style);
                }
            }
        }
    }
}

/// Un color de `palette.FRAME_CHARS` al azar — reemplaza
/// `random.choice(palette.FRAME_CHARS)`, repetido en varios efectos.
pub fn random_frame_char(frame_chars: &[char]) -> char {
    if frame_chars.is_empty() {
        return '░';
    }
    frame_chars[rand::thread_rng().gen_range(0..frame_chars.len())]
}

pub use transitions::{
    AfterimageEffect, ChromaticAberrationEffect, DatamoshEffect, SignalNoiseEffect, SyncSweepEffect, VignetteEffect,
};

/// Envuelve cualquiera de los 6 efectos de transición bajo una sola
/// interfaz — `App` guarda `Option<ActiveEffect>` sin necesitar saber cuál es.
pub enum ActiveEffect {
    SignalNoise(SignalNoiseEffect),
    ChromaticAberration(ChromaticAberrationEffect),
    Afterimage(AfterimageEffect),
    Datamosh(DatamoshEffect),
    Vignette(VignetteEffect),
    SyncSweep(SyncSweepEffect),
}

impl ActiveEffect {
    pub fn advance(&mut self, now: Instant, width: usize, height: usize, colors: &Colors) {
        match self {
            ActiveEffect::SignalNoise(e) => e.advance(now, width, height, colors),
            ActiveEffect::ChromaticAberration(e) => e.advance(now, width, height, colors),
            ActiveEffect::Afterimage(e) => e.advance(now, width, height, colors),
            ActiveEffect::Datamosh(e) => e.advance(now, width, height, colors),
            ActiveEffect::Vignette(e) => e.advance(now, width, height, colors),
            ActiveEffect::SyncSweep(e) => e.advance(now, width, height, colors),
        }
    }

    pub fn grid(&self) -> Option<&Grid> {
        match self {
            ActiveEffect::SignalNoise(e) => e.grid(),
            ActiveEffect::ChromaticAberration(e) => e.grid(),
            ActiveEffect::Afterimage(e) => e.grid(),
            ActiveEffect::Datamosh(e) => e.grid(),
            ActiveEffect::Vignette(e) => e.grid(),
            ActiveEffect::SyncSweep(e) => e.grid(),
        }
    }

    pub fn is_done(&self, now: Instant) -> bool {
        match self {
            ActiveEffect::SignalNoise(e) => e.is_done(now),
            ActiveEffect::ChromaticAberration(e) => e.is_done(now),
            ActiveEffect::Afterimage(e) => e.is_done(now),
            ActiveEffect::Datamosh(e) => e.is_done(now),
            ActiveEffect::Vignette(e) => e.is_done(now),
            ActiveEffect::SyncSweep(e) => e.is_done(now),
        }
    }
}
