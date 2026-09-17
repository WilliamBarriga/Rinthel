//! Puerto de `tui/effects/flicker.py` — `glitch_frames`/`GlitchLabel`. Sin
//! `FlickerLabel`/`TypewriterLabel`/`pulse`: no forman parte del inventario
//! de 8 efectos de esta sesión — ningún call site los usa (confirmado
//! grepeando `rinthel_tui/tui/screens/`).

use std::time::Instant;

use rand::Rng;

const CORRUPT_CHARS: &[char] = &['░', '▒', '▓', '█', '╳'];

/// `frames` strings que revelan `text` de izquierda a derecha a través de
/// caracteres de corrupción — el último siempre es el texto limpio. Puerto
/// 1:1 de `glitch_frames` (Python): ahí también se computa una sola vez
/// (`list(glitch_frames(...))` en `__init__`), no en cada frame.
pub fn glitch_frames(text: &str, frames: usize) -> Vec<String> {
    let chars: Vec<char> = text.chars().collect();
    let length = chars.len();
    let mut rng = rand::thread_rng();
    let mut out = Vec::with_capacity(frames + 1);
    for f in 0..frames {
        let reveal = length * (f + 1) / frames.max(1);
        let mut s = String::with_capacity(length);
        for (i, ch) in chars.iter().enumerate() {
            if i < reveal || *ch == ' ' {
                s.push(*ch);
            } else {
                s.push(CORRUPT_CHARS[rng.gen_range(0..CORRUPT_CHARS.len())]);
            }
        }
        out.push(s);
    }
    out.push(text.to_string());
    out
}

/// Puerto de `GlitchLabel`: revela `text` una sola vez desde `start()`,
/// consultado por reloj de pared en vez de `set_interval` — reusado por el
/// título del menú, el reveal de farewell, y como transición de
/// `RotatingTagline` entre frases.
pub struct GlitchReveal {
    frames: Vec<String>,
    frame_ms: u64,
    started: Instant,
}

impl GlitchReveal {
    pub fn start(text: &str, frames: usize, frame_ms: u64) -> Self {
        GlitchReveal { frames: glitch_frames(text, frames), frame_ms, started: Instant::now() }
    }

    pub fn text(&self, now: Instant) -> &str {
        let elapsed_ms = now.saturating_duration_since(self.started).as_millis() as u64;
        let idx = (elapsed_ms / self.frame_ms.max(1)) as usize;
        &self.frames[idx.min(self.frames.len() - 1)]
    }

    pub fn is_done(&self, now: Instant) -> bool {
        let elapsed_ms = now.saturating_duration_since(self.started).as_millis() as u64;
        (elapsed_ms / self.frame_ms.max(1)) as usize >= self.frames.len() - 1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn last_frame_is_always_clean_text() {
        let frames = glitch_frames("HOLA MUNDO", 8);
        assert_eq!(frames.last().unwrap(), "HOLA MUNDO");
        assert_eq!(frames.len(), 9);
    }

    #[test]
    fn spaces_never_corrupt() {
        for frame in glitch_frames("A B C", 5) {
            assert_eq!(frame.chars().nth(1), Some(' '));
            assert_eq!(frame.chars().nth(3), Some(' '));
        }
    }

    #[test]
    fn reveal_is_done_once_frames_run_out() {
        let reveal = GlitchReveal::start("HOLA", 4, 10);
        assert!(!reveal.is_done(reveal.started));
        let later = reveal.started + std::time::Duration::from_secs(1);
        assert!(reveal.is_done(later));
        assert_eq!(reveal.text(later), "HOLA");
    }
}
