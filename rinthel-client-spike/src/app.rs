//! Estado de la app (`App`/`AppEvent`/`Colors`) y el loop principal —
//! separado de `main.rs` en la sesión 00 del porteo (ver
//! .scratch/ratatui-migration/port-issues/00-scaffolding-testing-and-crate-skeleton.md).

use std::collections::{HashMap, VecDeque};
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

use crate::protocol::{
    self, CommandResult, ConfigPayload, ConfigSaveResult, CpuRamSample, DockerContainer, Envelope, GpuSample,
    PhaseLog, PhaseStatus, Theme,
};
use crate::screens::farewell::FarewellTimer;
use crate::screens::settings::{self, DetailRow};
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
    /// `llama_status` (sesión 08): estado parado, no un evento de corrida.
    LlamaStatus(bool),
    /// `GET /config` resuelto (sesión 09) — disparado al entrar a
    /// `ScreenId::Settings`, mismo trigger-on-entry que `MenuAction::Capture`.
    ConfigLoaded(ConfigPayload),
    ConfigLoadFailed(String),
    /// `POST /config` resuelto con `ok: true`.
    ConfigSaved { written: u32, warnings: Vec<String> },
    /// `ok: false` (errores de `RinthelConfig.validate()`) o falla de red —
    /// ambos se muestran igual (lista de líneas de error).
    ConfigSaveFailed(Vec<String>),
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

/// Qué panel de `SettingsScreen` recibe las teclas de navegación —
/// reemplaza el foco de widget que Textual manejaba solo (`Checkbox`/
/// `Button`/`Input` tenían cada uno su propio `on_*` en `settings.py`).
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ConfigFocus {
    Services,
    Detail,
}

/// Resultado del último `POST /config` — separado de
/// `last_command_result`/`last_command_error` (que asumen el shape
/// `CommandResult` de boot/terminate/reload/install) porque `/config`
/// tiene su propio shape (`ok`/`written`/`warnings`/`errors`).
pub enum ConfigSaveStatus {
    Saved(String),
    Failed(String),
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
    /// `llama_status` en vivo (sesión 08) — reemplaza el badge hardcodeado
    /// "N/A (spike)" que tenía `MonitorScreen` (llama-server no es un
    /// contenedor Docker, así que no sale de `containers`).
    pub llama_ready: bool,
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
    /// `GET /config` en curso o ya resuelto — `None` mientras carga (ver
    /// `screens::settings::draw`, que pinta "cargando…" en ese caso).
    pub config: Option<ConfigPayload>,
    pub config_selected_service: usize,
    /// Índice dentro de `settings::detail_rows(&service.fields)` del
    /// servicio seleccionado — se resetea a la primera fila seleccionable
    /// cada vez que cambia `config_selected_service`.
    pub config_selected_row: usize,
    pub config_focus: ConfigFocus,
    /// `Some(buffer)` mientras se edita el campo de texto seleccionado —
    /// reemplaza el `Input`/`Checkbox` con estado propio que tenía Textual;
    /// `None` en modo navegación.
    pub config_editing: Option<String>,
    /// env var -> valor nuevo (string), todo lo tocado en esta sesión de
    /// settings — mismo shape y mismo criterio que `self._edits` en
    /// `settings.py` (`config.diff_overrides`, del lado daemon, filtra qué
    /// de esto es un cambio real recién al guardar).
    pub config_edits: HashMap<String, String>,
    pub config_save_in_flight: bool,
    pub config_status: Option<ConfigSaveStatus>,
    should_quit: bool,
}

impl App {
    pub fn new(theme: &Theme) -> Self {
        App {
            screen: ScreenId::Menu,
            menu_selected: screens::first_selectable(),
            colors: Colors::from(theme),
            containers: Vec::new(),
            llama_ready: false,
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
            config: None,
            config_selected_service: 0,
            config_selected_row: 0,
            config_focus: ConfigFocus::Services,
            config_editing: None,
            config_edits: HashMap::new(),
            config_save_in_flight: false,
            config_status: None,
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
                if name == "boot" || name == "terminate" || name == "reload" || name == "install" {
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
            AppEvent::LlamaStatus(ready) => self.llama_ready = ready,
            AppEvent::ConfigLoaded(payload) => {
                self.config = Some(payload);
                self.config_selected_service = 0;
                self.config_selected_row = 0;
                self.config_focus = ConfigFocus::Services;
            }
            AppEvent::ConfigLoadFailed(err) => {
                self.config_status = Some(ConfigSaveStatus::Failed(format!("GET /config falló: {err}")));
            }
            AppEvent::ConfigSaved { written, warnings } => {
                self.config_save_in_flight = false;
                self.config_edits.clear();
                let msg = if written == 0 {
                    "nada para guardar — no tocaste ningún valor".to_string()
                } else {
                    format!("guardado ({written} cambio(s)) — aplica en el próximo BOOT/RELOAD")
                };
                let msg = if warnings.is_empty() { msg } else { format!("{msg} — {}", warnings.join("; ")) };
                self.config_status = Some(ConfigSaveStatus::Saved(msg));
            }
            AppEvent::ConfigSaveFailed(errors) => {
                self.config_save_in_flight = false;
                self.config_status = Some(ConfigSaveStatus::Failed(errors.join("; ")));
            }
        }
    }

    /// Puerto de `PhaseSequenceScreen._run_all`/`_run_closing`
    /// (`phase_runner.py`/`reload.py`): al llegar la respuesta bloqueante de
    /// `/boot`/`/terminate`/`/reload`/`/install`, cierra el log de la
    /// corrida — mensaje de cierre + banner si todo salió bien (y dispara
    /// farewell si fue TERMINATE), o "secuencia cortada" si algo falló. Los
    /// textos son los mismos que `_BOOT_CLOSING`/`_TERMINATE_CLOSING`/
    /// `_INSTALL_CLOSING`/el remate de `ReloadScreen._run_all` en Python; el
    /// efecto de transición que los precedía (y las 3 transiciones entre
    /// tandas de reload) quedan stubbeados (sesión 10 los retrofitea) — acá
    /// son líneas más del log.
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
                    "install" => ("Setup listo.", "SETUP LISTO — elegí [1] BOOT para levantar todo"),
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
        // `Divider` no es seleccionable (next_selectable/prev_selectable ya
        // lo garantizan), pero el match no puede probarlo — si algún día
        // deja de ser cierto, mejor no-op que panic.
        let Some(entry) = screens::MENU_ENTRIES[self.menu_selected].as_entry() else { return };
        match entry.action {
            MenuAction::Navigate(id) => self.screen = id,
            MenuAction::Boot => self.start_phase_run("boot", "/boot", "EXECUTE — FAST BOOT", tx),
            MenuAction::Reload => self.start_phase_run("reload", "/reload", "SYSTEM REBOOT", tx),
            MenuAction::Terminate => self.start_phase_run("terminate", "/terminate", "SHUTDOWN SEQUENCE", tx),
            MenuAction::Capture => {
                self.screen = ScreenId::Capture;
                self.command_in_flight = Some("capture");
                tokio::spawn(run_command("capture", "/capture", tx.clone()));
            }
            MenuAction::Install => self.start_phase_run("install", "/install", "INSTALL — SETUP INICIAL", tx),
            MenuAction::Settings => {
                self.screen = ScreenId::Settings;
                self.config = None;
                self.config_edits.clear();
                self.config_editing = None;
                self.config_status = None;
                self.config_save_in_flight = false;
                tokio::spawn(fetch_config(tx.clone()));
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

    /// Toda la lógica de teclado de `ScreenId::Settings` vive acá (no en
    /// `screens::settings`, que es solo dibujo + helpers puros) porque
    /// necesita mutar `App` y disparar `POST /config` — mismo criterio que
    /// `dispatch_menu_action`/`start_phase_run`. Consume la tecla entera, no
    /// cae al catch-all `q`=salir del loop principal: mientras se edita un
    /// campo de texto, cualquier char (incluido 'q') es contenido del
    /// campo, no un atajo — `settings.py` bindea igual `q`/Escape a
    /// "Volver" (no a salir de la app), mismo criterio que `LogsScreen`.
    fn handle_settings_key(&mut self, code: KeyCode, tx: &mpsc::UnboundedSender<AppEvent>) {
        if self.config_editing.is_none() && matches!(code, KeyCode::Char('q') | KeyCode::Esc) {
            self.screen = ScreenId::Menu;
            return;
        }
        let Some(payload) = self.config.clone() else { return }; // todavía cargando (GET /config)

        if self.config_editing.is_some() {
            match code {
                KeyCode::Enter | KeyCode::Esc => {
                    let buffer = self.config_editing.take().unwrap();
                    let svc = &payload.services[self.config_selected_service];
                    let rows = settings::detail_rows(&svc.fields);
                    if let DetailRow::Field(field_i) = rows[self.config_selected_row] {
                        self.config_edits.insert(svc.fields[field_i].env.clone(), buffer);
                    }
                }
                KeyCode::Backspace => {
                    if let Some(buffer) = &mut self.config_editing {
                        buffer.pop();
                    }
                }
                KeyCode::Char(c) => {
                    if let Some(buffer) = &mut self.config_editing {
                        buffer.push(c);
                    }
                }
                _ => {}
            }
            return;
        }

        match code {
            KeyCode::Left => self.config_focus = ConfigFocus::Services,
            KeyCode::Up => match self.config_focus {
                ConfigFocus::Services => {
                    self.config_selected_service = self.config_selected_service.saturating_sub(1);
                    self.config_selected_row = 0;
                }
                ConfigFocus::Detail => {
                    let svc = &payload.services[self.config_selected_service];
                    let rows = settings::detail_rows(&svc.fields);
                    self.config_selected_row = settings::prev_row(&rows, self.config_selected_row);
                }
            },
            KeyCode::Down => match self.config_focus {
                ConfigFocus::Services => {
                    self.config_selected_service =
                        (self.config_selected_service + 1).min(payload.services.len() - 1);
                    self.config_selected_row = 0;
                }
                ConfigFocus::Detail => {
                    let svc = &payload.services[self.config_selected_service];
                    let rows = settings::detail_rows(&svc.fields);
                    self.config_selected_row = settings::next_row(&rows, self.config_selected_row);
                }
            },
            KeyCode::Right | KeyCode::Enter if self.config_focus == ConfigFocus::Services => {
                let svc = &payload.services[self.config_selected_service];
                let rows = settings::detail_rows(&svc.fields);
                self.config_focus = ConfigFocus::Detail;
                self.config_selected_row = settings::first_row(&rows);
            }
            KeyCode::Char(' ') if self.config_focus == ConfigFocus::Services => {
                let svc = &payload.services[self.config_selected_service];
                if let (Some(orig), Some(env)) = (svc.enabled, &svc.enabled_env) {
                    let effective = self.config_edits.get(env).map(|v| v == "true").unwrap_or(orig);
                    self.config_edits.insert(env.clone(), (!effective).to_string());
                }
            }
            KeyCode::Enter | KeyCode::Char(' ') if self.config_focus == ConfigFocus::Detail => {
                let svc = &payload.services[self.config_selected_service];
                let rows = settings::detail_rows(&svc.fields);
                if let DetailRow::Field(field_i) = rows[self.config_selected_row] {
                    let field = &svc.fields[field_i];
                    if field.kind == "bool" {
                        let current = settings::field_value(self, field) == "true";
                        self.config_edits.insert(field.env.clone(), (!current).to_string());
                    } else {
                        self.config_editing = Some(settings::field_value(self, field).to_string());
                    }
                }
            }
            KeyCode::Char('s') if !self.config_save_in_flight => {
                self.config_save_in_flight = true;
                self.config_status = None;
                tokio::spawn(save_config(self.config_edits.clone(), tx.clone()));
            }
            _ => {}
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
                            // Settings maneja su propia tecla entera (ver
                            // doc-comment de `handle_settings_key`) — tiene
                            // que resolverse antes del catch-all de abajo,
                            // igual que Logs: mientras se edita un campo de
                            // texto, 'q' es contenido del campo, no salir.
                            (ScreenId::Settings, code) => self.handle_settings_key(code, &tx),
                            (_, KeyCode::Char('q')) => self.should_quit = true,
                            (ScreenId::Menu, KeyCode::Up) => {
                                self.menu_selected = screens::prev_selectable(self.menu_selected);
                            }
                            (ScreenId::Menu, KeyCode::Down) => {
                                self.menu_selected = screens::next_selectable(self.menu_selected);
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
                "llama_status" => serde_json::from_value::<protocol::LlamaStatus>(env.data)
                    .ok()
                    .map(|s| AppEvent::LlamaStatus(s.ready)),
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

/// `GET /config` (sesión 09) — disparado al entrar a `ScreenId::Settings`,
/// mismo trigger-on-entry que `run_command("capture", ...)`.
async fn fetch_config(tx: mpsc::UnboundedSender<AppEvent>) {
    let ev = match reqwest::get(format!("{DAEMON}/config")).await {
        Ok(resp) => match resp.json::<ConfigPayload>().await {
            Ok(payload) => AppEvent::ConfigLoaded(payload),
            Err(e) => AppEvent::ConfigLoadFailed(e.to_string()),
        },
        Err(e) => AppEvent::ConfigLoadFailed(e.to_string()),
    };
    let _ = tx.send(ev);
}

/// `POST /config` con el dict de overrides tocados en esta sesión de
/// settings (mismo shape que `config.diff_overrides` del lado daemon,
/// que hace el filtrado real). `ok: false` (validación) y falla de red
/// terminan ambas en `ConfigSaveFailed`, mostradas igual (líneas de error).
async fn save_config(overrides: HashMap<String, String>, tx: mpsc::UnboundedSender<AppEvent>) {
    let body = serde_json::json!({ "overrides": overrides });
    let ev = match reqwest::Client::new().post(format!("{DAEMON}/config")).json(&body).send().await {
        Ok(resp) => match resp.json::<ConfigSaveResult>().await {
            Ok(result) if result.ok => AppEvent::ConfigSaved { written: result.written, warnings: result.warnings },
            Ok(result) => AppEvent::ConfigSaveFailed(result.errors),
            Err(e) => AppEvent::ConfigSaveFailed(vec![e.to_string()]),
        },
        Err(e) => AppEvent::ConfigSaveFailed(vec![e.to_string()]),
    };
    let _ = tx.send(ev);
}
