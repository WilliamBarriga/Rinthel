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

use crate::protocol::{self, CommandResult, CpuRamSample, DockerContainer, Envelope, GpuSample, Theme};
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
                self.last_command_result = Some((name, result));
            }
            AppEvent::CommandFailed(name, err) => {
                self.command_in_flight = None;
                self.last_command_error = Some(format!("{name} falló: {err}"));
            }
        }
    }

    /// Reemplaza el `match app.menu_selected { 0 => ..., ... }` hardcodeado
    /// de antes de la sesión 00 — la semántica de cada opción vive en
    /// `screens::MENU_ENTRIES`, no acá.
    fn dispatch_menu_action(&mut self, tx: &mpsc::UnboundedSender<AppEvent>) {
        match screens::MENU_ENTRIES[self.menu_selected].action {
            MenuAction::Navigate(id) => self.screen = id,
            MenuAction::Boot => {
                self.command_in_flight = Some("boot");
                tokio::spawn(run_command("boot", "/boot", tx.clone()));
            }
            MenuAction::Terminate => {
                self.command_in_flight = Some("terminate");
                tokio::spawn(run_command("terminate", "/terminate", tx.clone()));
            }
            MenuAction::Quit => self.should_quit = true,
        }
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

                if event::poll(Duration::from_millis(80))? {
                    if let Event::Key(key) = event::read()? {
                        match (self.screen, key.code) {
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
                            (ScreenId::Monitor, KeyCode::Char('b')) => {
                                self.command_in_flight = Some("boot");
                                tokio::spawn(run_command("boot", "/boot", tx.clone()));
                            }
                            (ScreenId::Monitor, KeyCode::Char('t')) => {
                                self.command_in_flight = Some("terminate");
                                tokio::spawn(run_command("terminate", "/terminate", tx.clone()));
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
