//! Estado de la app (`App`/`AppEvent`/`Colors`) y el loop principal —
//! separado de `main.rs` en la sesión 00 del porteo (ver
//! .scratch/ratatui-migration/port-issues/00-scaffolding-testing-and-crate-skeleton.md).

use std::collections::VecDeque;
use std::io;
use std::time::Duration;

use crossterm::event::{self, Event, KeyCode};
use crossterm::execute;
use crossterm::terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen};
use futures_util::StreamExt;
use ratatui::backend::CrosstermBackend;
use ratatui::style::{Color, Style};
use ratatui::widgets::Block;
use ratatui::{Frame, Terminal};
use tokio::sync::mpsc;

use crate::protocol::{self, CommandResult, CpuRamSample, DockerContainer, Envelope, GpuSample, PhaseLog, PhaseStatus, Theme};
use crate::screens::farewell::FarewellTimer;
use crate::screens::{self, MenuAction, ScreenId};

pub const DAEMON: &str = "http://127.0.0.1:8765";
const WS: &str = "ws://127.0.0.1:8765/ws/monitor";
const HIST_LEN: usize = 60;

/// Eventos que las tareas de fondo empujan hacia el loop principal —
/// mismo patrón que un `Message` en Elm/TEA, adaptado a Rust con un canal.
pub enum AppEvent {
    Docker(Vec<DockerContainer>),
    Gpu(GpuSample),
    CpuRam(CpuRamSample),
    Log(String),
    CommandDone(&'static str, CommandResult),
    CommandFailed(&'static str, String),
    /// `phase_status` (amendment de docs/adr/0001, sesión 05): (label, status).
    PhaseStatus(String, String),
    /// `phase_log`: (kind, message).
    PhaseLog(String, String),
}

/// A qué pantalla vuelve `FarewellScreen` al terminar sus 5s — reemplaza el
/// `await push_screen_wait(FarewellScreen())` de Python (`app.rs` no tiene
/// stack de screens): `phase_runner.py:110` vuelve al checklist ya cerrado,
/// `menu.py:183` (EXIT) sale de la app.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum FarewellNext {
    BackToPhaseRunner,
    Quit,
}

pub struct Colors {
    pub fg: Color,
    pub accent: Color,
    pub warn: Color,
    pub success: Color,
    pub hot: Color,
    pub dim: Color,
    pub bg: Color,
}

fn hex(s: &str) -> Color {
    let s = s.trim_start_matches('#');
    let r = u8::from_str_radix(&s[0..2], 16).unwrap_or(255);
    let g = u8::from_str_radix(&s[2..4], 16).unwrap_or(255);
    let b = u8::from_str_radix(&s[4..6], 16).unwrap_or(255);
    Color::Rgb(r, g, b)
}

impl From<&Theme> for Colors {
    fn from(t: &Theme) -> Self {
        Colors {
            fg: hex(&t.canonical.fg),
            accent: hex(&t.canonical.accent),
            warn: hex(&t.canonical.warn),
            success: hex(&t.canonical.success),
            hot: hex(&t.canonical.hot),
            dim: hex(&t.canonical.dim),
            bg: hex(&t.canonical.bg),
        }
    }
}

pub struct App {
    pub screen: ScreenId,
    pub menu_selected: usize,
    pub colors: Colors,
    pub containers: Vec<DockerContainer>,
    pub gpu: GpuSample,
    pub cpu_ram: CpuRamSample,
    pub cpu_hist: VecDeque<u64>,
    pub ram_hist: VecDeque<u64>,
    pub gpu_hist: VecDeque<u64>,
    pub log_lines: VecDeque<String>,
    pub command_in_flight: Option<&'static str>,
    pub last_command_result: Option<(&'static str, CommandResult)>,
    pub last_command_error: Option<String>,
    /// Título de `PhaseRunnerScreen` para la corrida en curso — "EXECUTE —
    /// FAST BOOT" / "SHUTDOWN SEQUENCE", mismos textos que `menu.py`.
    pub phase_title: &'static str,
    /// Filas del checklist, en el orden en que llegó su primer evento
    /// `phase_status` — ver doc-comment de `widgets/checklist.rs`.
    pub phase_rows: Vec<(String, String)>,
    /// Log en vivo de la corrida — (kind, message), igual que `phase_log`.
    pub phase_log: VecDeque<(String, String)>,
    pub farewell_timer: Option<FarewellTimer>,
    pub farewell_next: FarewellNext,
    should_quit: bool,
}

impl App {
    pub fn new(theme: &Theme) -> Self {
        App {
            screen: ScreenId::Menu,
            menu_selected: 0,
            colors: Colors::from(theme),
            containers: Vec::new(),
            gpu: GpuSample::default(),
            cpu_ram: CpuRamSample::default(),
            cpu_hist: VecDeque::with_capacity(HIST_LEN),
            ram_hist: VecDeque::with_capacity(HIST_LEN),
            gpu_hist: VecDeque::with_capacity(HIST_LEN),
            log_lines: VecDeque::with_capacity(200),
            command_in_flight: None,
            last_command_result: None,
            last_command_error: None,
            phase_title: "",
            phase_rows: Vec::new(),
            phase_log: VecDeque::new(),
            farewell_timer: None,
            farewell_next: FarewellNext::Quit,
            should_quit: false,
        }
    }

    fn push_hist(hist: &mut VecDeque<u64>, v: u64) {
        if hist.len() == HIST_LEN {
            hist.pop_front();
        }
        hist.push_back(v);
    }

    fn apply(&mut self, ev: AppEvent) {
        match ev {
            AppEvent::Docker(c) => self.containers = c,
            AppEvent::Gpu(g) => {
                if let Some(u) = g.utilization {
                    Self::push_hist(&mut self.gpu_hist, u.round() as u64);
                }
                self.gpu = g;
            }
            AppEvent::CpuRam(c) => {
                Self::push_hist(&mut self.cpu_hist, c.cpu_percent.round() as u64);
                Self::push_hist(&mut self.ram_hist, c.ram_percent.round() as u64);
                self.cpu_ram = c;
            }
            AppEvent::Log(line) => {
                if self.log_lines.len() == 200 {
                    self.log_lines.pop_front();
                }
                self.log_lines.push_back(line);
            }
            AppEvent::CommandDone(name, result) => {
                self.command_in_flight = None;
                self.last_command_error = None;
                if name == "boot" || name == "terminate" || name == "reload" {
                    self.finish_phase_sequence(name, &result);
                }
                self.last_command_result = Some((name, result));
            }
            AppEvent::CommandFailed(name, err) => {
                self.command_in_flight = None;
                self.last_command_error = Some(format!("{name} falló: {err}"));
            }
            AppEvent::PhaseStatus(label, status) => {
                match self.phase_rows.iter_mut().find(|(l, _)| *l == label) {
                    Some(row) => row.1 = status,
                    None => self.phase_rows.push((label, status)),
                }
            }
            AppEvent::PhaseLog(kind, message) => {
                if self.phase_log.len() == 200 {
                    self.phase_log.pop_front();
                }
                self.phase_log.push_back((kind, message));
            }
        }
    }

    /// Puerto de `PhaseSequenceScreen._run_all`/`_run_closing`
    /// (`phase_runner.py`/`reload.py`): al llegar la respuesta bloqueante de
    /// `/boot`/`/terminate`/`/reload`, cierra el log de la corrida —
    /// mensaje de cierre + banner si todo salió bien (y dispara farewell si
    /// fue TERMINATE), o "secuencia cortada" si algo falló. Los textos son
    /// los mismos que `_BOOT_CLOSING`/`_TERMINATE_CLOSING`/el remate de
    /// `ReloadScreen._run_all` en Python; el efecto de transición que los
    /// precedía (y las 3 transiciones entre tandas de reload) quedan
    /// stubbeados (sesión 10 los retrofitea) — acá son líneas más del log.
    fn finish_phase_sequence(&mut self, name: &'static str, result: &CommandResult) {
        match result.results.iter().find(|r| !r.ok) {
            Some(failed) => {
                self.phase_log.push_back((
                    "error".to_string(),
                    format!("secuencia cortada: {}: {}", failed.service, failed.message),
                ));
            }
            None => {
                let (done_msg, banner) = match name {
                    "reload" => ("Reboot completo.", "SYSTEM REBOOTED — TODOS LOS SERVICIOS ACTIVOS"),
                    "boot" => ("Secuencia completa.", "TODO EN LINEA — Understory + Pithagoras activos"),
                    _ => ("Secuencia completa.", "SYSTEM OFFLINE — TODOS LOS SERVICIOS DETENIDOS"),
                };
                self.phase_log.push_back(("success".to_string(), done_msg.to_string()));
                self.phase_log.push_back(("success".to_string(), format!("◈ {banner}")));
                if name == "terminate" {
                    self.screen = ScreenId::Farewell;
                    self.farewell_timer = Some(FarewellTimer::start());
                    self.farewell_next = FarewellNext::BackToPhaseRunner;
                }
            }
        }
    }

    /// Reemplaza el `match app.menu_selected { 0 => ..., ... }` hardcodeado
    /// de antes de la sesión 00 — la semántica de cada opción vive en
    /// `screens::MENU_ENTRIES`, no acá.
    fn dispatch_menu_action(&mut self, tx: &mpsc::UnboundedSender<AppEvent>) {
        match screens::MENU_ENTRIES[self.menu_selected].action {
            MenuAction::Navigate(id) => self.screen = id,
            MenuAction::Boot => self.start_phase_run("boot", "/boot", "EXECUTE — FAST BOOT", tx),
            MenuAction::Reload => self.start_phase_run("reload", "/reload", "SYSTEM REBOOT", tx),
            MenuAction::Terminate => self.start_phase_run("terminate", "/terminate", "SHUTDOWN SEQUENCE", tx),
            MenuAction::Capture => {
                self.screen = ScreenId::Capture;
                self.command_in_flight = Some("capture");
                tokio::spawn(run_command("capture", "/capture", tx.clone()));
            }
            // menu.py:183 — EXIT pasa por FarewellScreen antes de salir,
            // igual que TERMINATE (grillado con Tarkark, sesión 05).
            MenuAction::Quit => {
                self.screen = ScreenId::Farewell;
                self.farewell_timer = Some(FarewellTimer::start());
                self.farewell_next = FarewellNext::Quit;
            }
        }
    }

    /// Boot/Terminate/Reload comparten el mismo arranque: limpiar el
    /// checklist/log de la corrida anterior, pasar a `PhaseRunnerScreen` y
    /// disparar el POST bloqueante — mismo trío que `menu.py`'s
    /// `_handle_selection` hace con `push_screen`/`run_worker`.
    fn start_phase_run(
        &mut self,
        name: &'static str,
        path: &'static str,
        title: &'static str,
        tx: &mpsc::UnboundedSender<AppEvent>,
    ) {
        self.phase_title = title;
        self.phase_rows.clear();
        self.phase_log.clear();
        self.screen = ScreenId::PhaseRunner;
        self.command_in_flight = Some(name);
        tokio::spawn(run_command(name, path, tx.clone()));
    }

    /// Loop principal: terminal alternate-screen, tick de eventos + polling
    /// de teclado, hasta `q`/SALIR. Antes vivía en `main()`.
    pub async fn run(mut self) -> io::Result<()> {
        let (tx, mut rx) = mpsc::unbounded_channel::<AppEvent>();
        tokio::spawn(ws_task(tx.clone()));

        enable_raw_mode()?;
        let mut stdout = io::stdout();
        execute!(stdout, EnterAlternateScreen)?;
        let backend = CrosstermBackend::new(stdout);
        let mut terminal = Terminal::new(backend)?;

        let result = (async {
            loop {
                terminal.draw(|f| draw(f, &self))?;

                while let Ok(ev) = rx.try_recv() {
                    self.apply(ev);
                }

                // `FarewellScreen._finish` de Python (set_timer + dismiss()):
                // acá no hay callback, así que se consulta el timer cada
                // vuelta del loop en vez de agendar uno.
                if self.screen == ScreenId::Farewell {
                    if let Some(timer) = &self.farewell_timer {
                        if timer.is_done() {
                            self.farewell_timer = None;
                            match self.farewell_next {
                                FarewellNext::Quit => self.should_quit = true,
                                FarewellNext::BackToPhaseRunner => self.screen = ScreenId::PhaseRunner,
                            }
                        }
                    }
                }

                if event::poll(Duration::from_millis(80))? {
                    if let Event::Key(key) = event::read()? {
                        match (self.screen, key.code) {
                            // LogsScreen (rinthel_tui/tui/screens/logs.py) bindea
                            // q/Escape a "volver", no a "salir" — tiene que
                            // resolverse antes del catch-all de abajo.
                            (ScreenId::Logs, KeyCode::Char('q') | KeyCode::Esc) => {
                                self.screen = ScreenId::Menu;
                            }
                            (_, KeyCode::Char('q')) => self.should_quit = true,
                            (ScreenId::Menu, KeyCode::Up) => {
                                self.menu_selected = self.menu_selected.saturating_sub(1);
                            }
                            (ScreenId::Menu, KeyCode::Down) => {
                                self.menu_selected =
                                    (self.menu_selected + 1).min(screens::MENU_ENTRIES.len() - 1);
                            }
                            (ScreenId::Menu, KeyCode::Enter) => self.dispatch_menu_action(&tx),
                            (ScreenId::Monitor, KeyCode::Esc) => self.screen = ScreenId::Menu,
                            // CaptureScreen/PhaseRunnerScreen bloquean "volver"
                            // hasta terminar (`action_dismiss_if_done` en
                            // capture.py/phase_runner.py) — acá eso es "no hay
                            // POST en vuelo".
                            (ScreenId::Capture, KeyCode::Esc) if screens::capture::done(&self) => {
                                self.screen = ScreenId::Menu;
                            }
                            (ScreenId::PhaseRunner, KeyCode::Esc) if screens::phase_runner::done(&self) => {
                                self.screen = ScreenId::Menu;
                            }
                            _ => {}
                        }
                    }
                }

                if self.should_quit {
                    break;
                }
            }
            Ok::<(), io::Error>(())
        })
        .await;

        disable_raw_mode()?;
        execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
        terminal.show_cursor()?;

        result
    }
}

fn draw(f: &mut Frame, app: &App) {
    let bg = Block::default().style(Style::default().bg(app.colors.bg));
    f.render_widget(bg, f.area());
    screens::draw(app.screen, f, app);
}

async fn ws_task(tx: mpsc::UnboundedSender<AppEvent>) {
    loop {
        let conn = tokio_tungstenite::connect_async(WS).await;
        let Ok((stream, _)) = conn else {
            tokio::time::sleep(Duration::from_secs(2)).await;
            continue;
        };
        let (_write, mut read) = stream.split();
        while let Some(Ok(msg)) = read.next().await {
            let tokio_tungstenite::tungstenite::Message::Text(text) = msg else { continue };
            let Ok(env) = serde_json::from_str::<Envelope>(&text) else { continue };
            let ev = match env.kind.as_str() {
                "docker_status" => serde_json::from_value::<protocol::DockerStatus>(env.data)
                    .ok()
                    .map(|d| AppEvent::Docker(d.containers)),
                "gpu_sample" => serde_json::from_value::<GpuSample>(env.data).ok().map(AppEvent::Gpu),
                "cpu_ram_sample" => serde_json::from_value::<CpuRamSample>(env.data).ok().map(AppEvent::CpuRam),
                "log_line" => serde_json::from_value::<protocol::LogLine>(env.data)
                    .ok()
                    .map(|l| AppEvent::Log(l.line)),
                "phase_status" => serde_json::from_value::<PhaseStatus>(env.data)
                    .ok()
                    .map(|p| AppEvent::PhaseStatus(p.label, p.status)),
                "phase_log" => serde_json::from_value::<PhaseLog>(env.data)
                    .ok()
                    .map(|p| AppEvent::PhaseLog(p.kind, p.message)),
                _ => None,
            };
            if let Some(ev) = ev {
                if tx.send(ev).is_err() {
                    return;
                }
            }
        }
        // reconexión sin replay (ADR 0001): volvemos al top del loop y
        // el próximo connect trae estado fresco.
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}

async fn run_command(name: &'static str, path: &str, tx: mpsc::UnboundedSender<AppEvent>) {
    let url = format!("{DAEMON}{path}");
    match reqwest::Client::new().post(&url).send().await {
        Ok(resp) => match resp.json::<CommandResult>().await {
            Ok(result) => {
                let _ = tx.send(AppEvent::CommandDone(name, result));
            }
            Err(e) => {
                let _ = tx.send(AppEvent::CommandFailed(name, e.to_string()));
            }
        },
        Err(e) => {
            let _ = tx.send(AppEvent::CommandFailed(name, e.to_string()));
        }
    }
}
