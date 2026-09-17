//! Puerto de `tui/effects/tagline.py` — `RotatingTagline`: cicla frases,
//! revelando cada una con la misma transición glitch que `GlitchLabel`
//! (`flicker::GlitchReveal`) reusada acá, igual que en Python
//! (`from ...flicker import glitch_frames`).

use std::time::{Duration, Instant};

use rand::seq::SliceRandom;

use super::flicker::GlitchReveal;

pub struct RotatingTagline {
    lines: Vec<String>,
    index: usize,
    interval: Duration,
    transition_frames: usize,
    frame_ms: u64,
    next_rotation: Instant,
    transition: Option<GlitchReveal>,
}

impl RotatingTagline {
    pub fn new(lines: &[&str], interval_s: f64, transition_frames: usize, frame_ms: u64) -> Self {
        let mut lines: Vec<String> = lines.iter().map(|s| (*s).to_string()).collect();
        lines.shuffle(&mut rand::thread_rng());
        let interval = Duration::from_secs_f64(interval_s);
        RotatingTagline {
            lines,
            index: 0,
            interval,
            transition_frames,
            frame_ms,
            next_rotation: Instant::now() + interval,
            transition: None,
        }
    }

    /// Llamado cada vuelta del loop principal mientras el menú está activo
    /// — reemplaza los dos `set_interval` de Python (rotación + frames de
    /// transición) por un chequeo de reloj de pared.
    pub fn advance(&mut self, now: Instant) {
        if let Some(t) = &self.transition {
            if t.is_done(now) {
                self.transition = None;
            }
        }
        if self.transition.is_none() && now >= self.next_rotation && self.lines.len() > 1 {
            self.index = (self.index + 1) % self.lines.len();
            self.transition = Some(GlitchReveal::start(&self.lines[self.index], self.transition_frames, self.frame_ms));
            self.next_rotation = now + self.interval;
        }
    }

    pub fn text(&self, now: Instant) -> &str {
        match &self.transition {
            Some(t) => t.text(now),
            None => &self.lines[self.index],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn starts_on_first_line_no_transition() {
        let tagline = RotatingTagline::new(&["uno", "dos"], 6.0, 6, 40);
        let now = Instant::now();
        assert!(tagline.lines.contains(&tagline.text(now).to_string()));
    }

    #[test]
    fn rotates_after_interval_elapses() {
        let mut tagline = RotatingTagline::new(&["uno", "dos", "tres"], 0.01, 4, 5);
        let first = tagline.index;
        std::thread::sleep(Duration::from_millis(15));
        tagline.advance(Instant::now());
        assert_ne!(tagline.index, first);
    }
}
