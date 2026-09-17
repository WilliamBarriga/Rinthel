//! Puerto de 5 de los 6 `TransitionEffect` de `tui/effects/transitions.py`
//! que algún call site usa (`SignalNoiseEffect`/`ChromaticAberrationEffect`/
//! `AfterimageEffect`/`DatamoshEffect`/`VignetteEffect` — no
//! `ScreenTearEffect`/`ScanlinesEffect`, sin caller en la app), más
//! [`SyncSweepEffect`], que no es un puerto: reemplaza a `RippleEffect`
//! como remate de `/reload` (Tarkark, sesión 10, probando en vivo: el
//! original resultaba "demasiado largo y feo" en la terminal real).
//!
//! Cada uno guarda su propio reloj interno (`next_at`, cuándo le toca el
//! próximo cambio de frame) y se avanza por `Instant` en vez de
//! `await asyncio.sleep` — ver doc-comment de `effects::mod` para el porqué.
//! La matemática generativa replica la de Python; lo que cambia es que acá
//! cada `run()` se "desenrolla" a mano en un método `advance()` llamado
//! desde el loop principal.

use std::time::{Duration, Instant};

use rand::Rng;
use ratatui::style::{Color, Modifier, Style};

use super::{blank_grid, random_frame_char, Grid};
use crate::app::Colors;

// ── SignalNoiseEffect ───────────────────────────────────────────────────

/// Banda de interferencia horizontal que se desplaza hacia abajo — usada
/// antes de toda transición de menú que dispara un comando (BOOT/RELOAD/
/// TERMINATE/CAPTURE/INSTALL), igual que `menu.py:154-176`.
pub struct SignalNoiseEffect {
    duration: Duration,
    band_height: usize,
    speed: Duration,
    started: Instant,
    next_at: Instant,
    band_start: usize,
    band_ready: bool,
    showing: bool,
    grid: Option<Grid>,
}

impl SignalNoiseEffect {
    pub fn new(duration_s: f64, band_height: usize, speed_ms: u64) -> Self {
        let now = Instant::now();
        SignalNoiseEffect {
            duration: Duration::from_secs_f64(duration_s),
            band_height: band_height.max(1),
            speed: Duration::from_millis(speed_ms),
            started: now,
            next_at: now,
            band_start: 0,
            band_ready: false,
            showing: false,
            grid: None,
        }
    }

    #[allow(clippy::needless_range_loop)] // `row`/`col` alimentan más matemática que solo indexar (rango de banda, roll por celda)
    pub fn advance(&mut self, now: Instant, width: usize, height: usize, colors: &Colors) {
        if now < self.next_at {
            return;
        }
        let height = height.max(1);
        if !self.band_ready {
            self.band_start = rand::thread_rng().gen_range(0..height);
            self.band_ready = true;
        }
        if self.showing {
            self.grid = None;
            self.showing = false;
            self.band_start = (self.band_start + 1) % height;
        } else {
            let palette = [colors.hot_dim, colors.electric_dim, colors.steel_dim];
            let style = Style::default().fg(palette[rand::thread_rng().gen_range(0..palette.len())]);
            let mut grid = blank_grid(width, height);
            let band_end = (self.band_start + self.band_height).min(height);
            let mut rng = rand::thread_rng();
            for row in self.band_start..band_end {
                for col in 0..width {
                    let r: f64 = rng.gen();
                    let ch = if r < 0.2 {
                        random_frame_char(&colors.frame_chars)
                    } else if r < 0.4 {
                        '░'
                    } else if r < 0.6 {
                        '▒'
                    } else {
                        ' '
                    };
                    grid[row][col] = (ch, Some(style));
                }
            }
            self.grid = Some(grid);
            self.showing = true;
        }
        self.next_at = now + self.speed;
    }

    pub fn grid(&self) -> Option<&Grid> {
        self.grid.as_ref()
    }

    pub fn is_done(&self, now: Instant) -> bool {
        now.saturating_duration_since(self.started) >= self.duration
    }
}

// ── ChromaticAberrationEffect ───────────────────────────────────────────

/// Separación RGB — capas roja/verde/azul jitterean por separado. Cierre de
/// BOOT/INSTALL exitosos (`_BOOT_CLOSING`/`_INSTALL_CLOSING`).
pub struct ChromaticAberrationEffect {
    text: String,
    duration: Duration,
    started: Instant,
    next_at: Instant,
    grid: Option<Grid>,
}

impl ChromaticAberrationEffect {
    pub fn new(text: &str, duration_s: f64) -> Self {
        let now = Instant::now();
        ChromaticAberrationEffect {
            text: text.to_string(),
            duration: Duration::from_secs_f64(duration_s),
            started: now,
            next_at: now,
            grid: None,
        }
    }

    fn place(grid: &mut Grid, row: i64, col: i64, text: &str, style: Style, width: usize, height: usize) {
        if row < 0 || row as usize >= height {
            return;
        }
        let row = row as usize;
        for (i, ch) in text.chars().enumerate() {
            let c = col + i as i64;
            if c >= 0 && (c as usize) < width {
                grid[row][c as usize] = (ch, Some(style));
            }
        }
    }

    pub fn advance(&mut self, now: Instant, width: usize, height: usize, colors: &Colors) {
        if now < self.next_at {
            return;
        }
        let center_row = (height / 2) as i64;
        let text_len = self.text.chars().count() as i64;
        let center_col = 3.max((width as i64 - text_len) / 2);
        let mut rng = rand::thread_rng();
        let r_offset: i64 = rng.gen_range(-1..=1);
        let b_offset: i64 = rng.gen_range(-1..=1);
        let mut grid = blank_grid(width, height);
        let red = Style::default().fg(Color::Rgb(0xFF, 0x00, 0x00));
        let blue = Style::default().fg(Color::Rgb(0x00, 0x87, 0xFF));
        let green = Style::default().fg(colors.glow);
        Self::place(&mut grid, center_row - 1, center_col + r_offset, &self.text, red, width, height);
        Self::place(&mut grid, center_row, center_col, &self.text, green, width, height);
        Self::place(&mut grid, center_row + 1, center_col + b_offset, &self.text, blue, width, height);
        self.grid = Some(grid);
        self.next_at = now + Duration::from_millis(80);
    }

    pub fn grid(&self) -> Option<&Grid> {
        self.grid.as_ref()
    }

    pub fn is_done(&self, now: Instant) -> bool {
        now.saturating_duration_since(self.started) >= self.duration
    }
}

// ── AfterimageEffect ─────────────────────────────────────────────────────

/// Texto con ghosting tipo fósforo CRT — flash, apagón, fantasma, fade.
/// Cierre de TERMINATE (`_TERMINATE_CLOSING`). A diferencia de los demás,
/// es una secuencia FIJA de pasos (no un loop que se re-randomiza) — igual
/// que Python, cada frame se computa una sola vez y la línea de tiempo se
/// arma en el primer `advance()` (recién ahí se conoce el `width`/`height`
/// reales, que `new()` no tiene).
pub struct AfterimageEffect {
    text: String,
    started: Instant,
    timeline: Option<Vec<(Duration, Option<Grid>)>>,
    idx: usize,
}

const AFTERIMAGE_TOTAL_SECS: f64 = 3.3;

impl AfterimageEffect {
    pub fn new(text: &str) -> Self {
        AfterimageEffect { text: text.to_string(), started: Instant::now(), timeline: None, idx: 0 }
    }

    fn frame(&self, chars: &str, style: Style, width: usize, height: usize) -> Grid {
        let mut grid = blank_grid(width, height);
        let row = height / 2;
        if row >= height {
            return grid;
        }
        let text_len = self.text.chars().count() as i64;
        let col0 = 0.max((width as i64 - text_len) / 2) as usize;
        for (i, ch) in chars.chars().enumerate() {
            let c = col0 + i;
            if c < width && ch != ' ' {
                grid[row][c] = (ch, Some(style));
            }
        }
        grid
    }

    /// `keep_prob` = probabilidad de que un caracter sobreviva — mismo
    /// signo que los 3 generators de Python (`ch if random() > x else ' '`
    /// / `< x`), solo reexpresado como "probabilidad de mantener".
    fn corrupt(text: &str, keep_prob: f64, rng: &mut impl Rng) -> String {
        text.chars().map(|ch| if rng.gen::<f64>() < keep_prob { ch } else { ' ' }).collect()
    }

    fn build(&self, width: usize, height: usize, colors: &Colors) -> Vec<(Duration, Option<Grid>)> {
        let mut rng = rand::thread_rng();
        let text = self.text.clone();
        vec![
            (
                Duration::ZERO,
                Some(self.frame(&text, Style::default().fg(colors.steel).add_modifier(Modifier::BOLD), width, height)),
            ),
            (Duration::from_secs_f64(1.0), None),
            (Duration::from_secs_f64(1.1), Some(self.frame(&text, Style::default().fg(colors.electric), width, height))),
            (
                Duration::from_secs_f64(1.7),
                Some(self.frame(&text, Style::default().fg(colors.electric_dim), width, height)),
            ),
            (
                Duration::from_secs_f64(2.2),
                Some(self.frame(&Self::corrupt(&text, 2.0 / 3.0, &mut rng), Style::default().fg(colors.cool_dim), width, height)),
            ),
            (
                Duration::from_secs_f64(2.6),
                Some(self.frame(&Self::corrupt(&text, 0.5, &mut rng), Style::default().fg(colors.dim), width, height)),
            ),
            (
                Duration::from_secs_f64(3.0),
                Some(self.frame(&Self::corrupt(&text, 0.2, &mut rng), Style::default().fg(colors.dim), width, height)),
            ),
            (Duration::from_secs_f64(AFTERIMAGE_TOTAL_SECS), None),
        ]
    }

    pub fn advance(&mut self, now: Instant, width: usize, height: usize, colors: &Colors) {
        if self.timeline.is_none() {
            self.timeline = Some(self.build(width, height, colors));
        }
        let elapsed = now.saturating_duration_since(self.started);
        if let Some(tl) = &self.timeline {
            self.idx = tl.iter().rposition(|(t, _)| elapsed >= *t).unwrap_or(0);
        }
    }

    pub fn grid(&self) -> Option<&Grid> {
        self.timeline.as_ref().and_then(|tl| tl.get(self.idx)).and_then(|(_, g)| g.as_ref())
    }

    pub fn is_done(&self, now: Instant) -> bool {
        now.saturating_duration_since(self.started) >= Duration::from_secs_f64(AFTERIMAGE_TOTAL_SECS)
    }
}

// ── DatamoshEffect ───────────────────────────────────────────────────────

/// Bloques rectangulares de basura que aparecen y desaparecen — códec roto.
/// Primera de las 2 transiciones entre tandas de `/reload` (amendment de
/// docs/adr/0001, sesión 10): dispara al recibir `phase_batch{batch:"boot"}`
/// (límite shutdown→boot).
pub struct DatamoshEffect {
    duration: Duration,
    intensity: u32,
    started: Instant,
    next_at: Instant,
    showing: bool,
    grid: Option<Grid>,
}

impl DatamoshEffect {
    pub fn new(duration_s: f64, intensity: u32) -> Self {
        let now = Instant::now();
        DatamoshEffect {
            duration: Duration::from_secs_f64(duration_s),
            intensity: intensity.max(1),
            started: now,
            next_at: now,
            showing: false,
            grid: None,
        }
    }

    pub fn advance(&mut self, now: Instant, width: usize, height: usize, colors: &Colors) {
        if now < self.next_at {
            return;
        }
        let intensity = self.intensity as f64;
        if self.showing {
            self.grid = None;
            self.showing = false;
            self.next_at = now + Duration::from_secs_f64(0.03 / intensity + 0.01);
            return;
        }
        let width = width.max(1);
        let height = height.max(1);
        let palette = [colors.accent, colors.hot, colors.electric];
        let mut rng = rand::thread_rng();
        let mut grid = blank_grid(width, height);
        for b in 0..self.intensity {
            let bw = rng.gen_range(5..=19).min(width);
            let bh = rng.gen_range(1..=3).min(height);
            let dst_row = rng.gen_range(0..=height - bh);
            let dst_col = rng.gen_range(0..=width - bw);
            let style = Style::default().fg(palette[(b as usize) % palette.len()]);
            for r in 0..bh {
                let row = dst_row + r;
                if row >= height {
                    continue;
                }
                for c in 0..bw {
                    let col = dst_col + c;
                    if col >= width {
                        continue;
                    }
                    let roll: f64 = rng.gen();
                    let ch = if roll < 0.33 {
                        random_frame_char(&colors.frame_chars)
                    } else if roll < 0.66 {
                        '▓'
                    } else {
                        '░'
                    };
                    grid[row][col] = (ch, Some(style));
                }
            }
        }
        self.grid = Some(grid);
        self.showing = true;
        self.next_at = now + Duration::from_secs_f64(0.06 / intensity + 0.02);
    }

    pub fn grid(&self) -> Option<&Grid> {
        self.grid.as_ref()
    }

    pub fn is_done(&self, now: Instant) -> bool {
        now.saturating_duration_since(self.started) >= self.duration
    }
}

// ── VignetteEffect ───────────────────────────────────────────────────────

/// Bordes/esquinas oscurecidos — foco claustrofóbico al centro. Segunda de
/// las 2 transiciones entre tandas de `/reload`: dispara al recibir
/// `phase_batch{batch:"rebuild"}` (límite boot→rebuild).
pub struct VignetteEffect {
    duration: Duration,
    intensity: i64,
    started: Instant,
    next_at: Instant,
    showing: bool,
    grid: Option<Grid>,
}

impl VignetteEffect {
    pub fn new(duration_s: f64, intensity: i64) -> Self {
        let now = Instant::now();
        VignetteEffect {
            duration: Duration::from_secs_f64(duration_s),
            intensity,
            started: now,
            next_at: now,
            showing: false,
            grid: None,
        }
    }

    #[allow(clippy::needless_range_loop)] // `row`/`col` alimentan la distancia al borde, no solo el índice
    pub fn advance(&mut self, now: Instant, width: usize, height: usize, colors: &Colors) {
        if now < self.next_at {
            return;
        }
        let mut rng = rand::thread_rng();
        if self.showing {
            self.grid = None;
            self.showing = false;
            self.next_at = now + Duration::from_secs_f64(0.6 + rng.gen_range(0.0..0.3));
            return;
        }
        let width = width.max(1);
        let height = height.max(1);
        let mut grid = blank_grid(width, height);
        let style = Style::default().fg(colors.accent);
        for row in 0..height {
            let row_dist = ((row + 1).min(height - row)) as i64;
            for col in 0..width {
                let col_dist = ((col + 1).min(width - col)) as i64;
                let dist = row_dist.min(col_dist);
                if dist <= self.intensity {
                    let ch = match dist {
                        1 => '█',
                        2 => '▓',
                        3 => '▒',
                        4 => '░',
                        _ => '░',
                    };
                    grid[row][col] = (ch, Some(style));
                }
            }
        }
        self.grid = Some(grid);
        self.showing = true;
        self.next_at = now + Duration::from_secs_f64(0.2 + rng.gen_range(0.8..1.2));
    }

    pub fn grid(&self) -> Option<&Grid> {
        self.grid.as_ref()
    }

    pub fn is_done(&self, now: Instant) -> bool {
        now.saturating_duration_since(self.started) >= self.duration
    }
}

// ── SyncSweepEffect ──────────────────────────────────────────────────────

/// Barrido horizontal único, de arriba a abajo, con una cola de 2 renglones
/// que se apaga detrás — remate de `/reload` tras la última tanda (rebuild)
/// exitosa, sin protocolo nuevo: dispara sobre `CommandDone`, igual que el
/// `RippleEffect` (retirado) al que reemplaza.
///
/// No es un puerto de ningún `effect_*` de Python — Tarkark, sesión 10,
/// probando en vivo: el `RippleEffect` original (anillos concéntricos
/// expandiéndose) resultaba "demasiado largo y feo" en la terminal real.
/// Reemplazo deliberadamente simple (líneas rectas, sin ruido aleatorio,
/// nada de geometría de círculo/elipse) y de duración fija corta — mismo
/// margen "llamativas pero cortas, 3s máximo" que ya había dado para las
/// transiciones de reload.
pub struct SyncSweepEffect {
    duration: Duration,
    next_at: Instant,
    step: usize,
    steps_total: usize,
    grid: Option<Grid>,
    /// Distinto de `step >= steps_total`: ese es el tick que borra la
    /// última cola (`grid = None`) — recién ahí termina de verdad. Sin este
    /// flag, `is_done()` se pondría `true` un tick antes, en el mismo en
    /// que se pintó el último frame — `App::run` lo saca de
    /// `active_effect` ese mismo tick, sin llegar a dibujarlo nunca.
    finished: bool,
}

impl SyncSweepEffect {
    pub fn new(duration_s: f64) -> Self {
        let now = Instant::now();
        SyncSweepEffect {
            duration: Duration::from_secs_f64(duration_s),
            next_at: now,
            step: 0,
            steps_total: 0,
            grid: None,
            finished: false,
        }
    }

    pub fn advance(&mut self, now: Instant, width: usize, height: usize, colors: &Colors) {
        if now < self.next_at {
            return;
        }
        if self.steps_total == 0 {
            // +2 para que la cola termine de apagarse después de cruzar el
            // último renglón, en vez de cortar de golpe con la cabeza del
            // barrido todavía visible.
            self.steps_total = height.max(1) + 2;
        }
        if self.step >= self.steps_total {
            self.grid = None;
            self.finished = true;
            return;
        }
        let mut grid = blank_grid(width, height);
        let head = self.step as i64;
        let rows: [(i64, Style); 3] = [
            (head, Style::default().fg(colors.glow).add_modifier(Modifier::BOLD)),
            (head - 1, Style::default().fg(colors.success)),
            (head - 2, Style::default().fg(colors.dim)),
        ];
        for (row, style) in rows {
            if row >= 0 && (row as usize) < height {
                for cell in grid[row as usize].iter_mut() {
                    *cell = ('─', Some(style));
                }
            }
        }
        self.grid = Some(grid);
        self.step += 1;
        let step_secs = self.duration.as_secs_f64() / self.steps_total as f64;
        self.next_at = now + Duration::from_secs_f64(step_secs.max(0.01));
    }

    pub fn grid(&self) -> Option<&Grid> {
        self.grid.as_ref()
    }

    pub fn is_done(&self, _now: Instant) -> bool {
        self.finished
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_colors() -> Colors {
        Colors {
            fg: Color::White,
            accent: Color::Magenta,
            warn: Color::Yellow,
            success: Color::Green,
            hot: Color::Red,
            dim: Color::Gray,
            bg: Color::Black,
            electric: Color::LightMagenta,
            glow: Color::White,
            cool: Color::Cyan,
            cool_dim: Color::DarkGray,
            hot_dim: Color::Red,
            electric_dim: Color::Magenta,
            steel: Color::Gray,
            steel_dim: Color::DarkGray,
            frame_chars: vec!['░', '▒', '▓', '█'],
        }
    }

    #[test]
    fn signal_noise_is_done_after_duration() {
        let colors = test_colors();
        let mut effect = SignalNoiseEffect::new(1.0, 3, 20);
        let now = Instant::now();
        effect.advance(now, 40, 10, &colors);
        assert!(effect.grid().is_some());
        assert!(!effect.is_done(now));
        assert!(effect.is_done(now + Duration::from_secs(2)));
    }

    #[test]
    fn chromatic_aberration_places_three_layers() {
        let colors = test_colors();
        let mut effect = ChromaticAberrationEffect::new("HI", 1.0);
        let now = Instant::now();
        effect.advance(now, 20, 10, &colors);
        let grid = effect.grid().expect("debería haber grid recién arrancado");
        let painted: usize = grid.iter().flatten().filter(|(ch, _)| *ch != ' ').count();
        assert!(painted >= 4); // "HI" x 2 capas seguro (red/blue jitterean, green siempre en (5,centro))
    }

    #[test]
    fn afterimage_ends_blank_after_total_duration() {
        let colors = test_colors();
        let mut effect = AfterimageEffect::new("BYE");
        let start = Instant::now();
        effect.advance(start, 20, 5, &colors);
        assert!(effect.grid().is_some());
        let done_at = start + Duration::from_secs_f64(AFTERIMAGE_TOTAL_SECS + 0.1);
        effect.advance(done_at, 20, 5, &colors);
        assert!(effect.is_done(done_at));
        assert!(effect.grid().is_none());
    }

    #[test]
    fn datamosh_blinks_on_then_off() {
        let colors = test_colors();
        let mut effect = DatamoshEffect::new(2.0, 2);
        let now = Instant::now();
        effect.advance(now, 30, 10, &colors);
        assert!(effect.grid().is_some());
        let off_at = effect.next_at;
        effect.advance(off_at, 30, 10, &colors);
        assert!(effect.grid().is_none());
    }

    #[test]
    fn vignette_darkens_corners_only_within_intensity() {
        let colors = test_colors();
        let mut effect = VignetteEffect::new(2.0, 1);
        let now = Instant::now();
        effect.advance(now, 20, 10, &colors);
        let grid = effect.grid().unwrap();
        assert_eq!(grid[0][0].0, '█'); // esquina: dist=1
        assert_eq!(grid[5][10].0, ' '); // centro: fuera del intensity=1
    }

    #[test]
    fn sync_sweep_paints_a_full_width_line_at_the_head() {
        let colors = test_colors();
        let mut effect = SyncSweepEffect::new(0.5);
        let now = Instant::now();
        effect.advance(now, 20, 10, &colors);
        let grid = effect.grid().expect("primer frame debería pintar la línea inicial");
        let painted_in_row0 = grid[0].iter().filter(|(ch, _)| *ch != ' ').count();
        assert_eq!(painted_in_row0, 20);
    }

    #[test]
    fn sync_sweep_finishes_after_crossing_the_screen_plus_trail() {
        let colors = test_colors();
        let mut effect = SyncSweepEffect::new(0.3);
        let mut now = Instant::now();
        for _ in 0..500 {
            effect.advance(now, 20, 10, &colors);
            if effect.is_done(now) {
                break;
            }
            now += Duration::from_millis(5);
        }
        assert!(effect.is_done(now));
        assert!(effect.grid().is_none());
    }
}
