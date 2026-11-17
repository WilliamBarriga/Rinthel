//! Estado de la app (`App`/`AppEvent`/`Colors`) y el loop principal.

use std::collections::{HashMap, VecDeque};
use std::io;
use std::sync::{LazyLock, OnceLock, RwLock};
use std::time::{Duration, Instant};

use crossterm::event::{self, Event, KeyCode};
use crossterm::execute;
use crossterm::terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen};
use futures_util::StreamExt;
use ratatui::backend::CrosstermBackend;
use ratatui::style::{Color, Style};
use ratatui::widgets::Block;
use ratatui::{Frame, Terminal};
use tokio::sync::mpsc;

use crate::effects::{self, ActiveEffect};
use crate::protocol::{
    self, CommandResult, ConfigPayload, ConfigSaveResult, CpuRamSample, DockerContainer, Envelope, GpuSample,
    ModelsStatus, PhaseLog, PhaseStatus, RotateResult, Theme,
};
use crate::screens::exit_prompt::ExitPromptTimer;
use crate::screens::farewell::FarewellTimer;
use crate::screens::settings::{ConfigFocus, ConfigSaveStatus, SecretKey, SettingsState};
use crate::screens::{self, MenuAction, ScreenId};

/// Frases que rota `RotatingTagline` en el menú — mezcla status técnico con
/// líneas de peso narrativo, mismo registro que la cita de Blade Runner del
/// banner.
pub const TAGLINES: &[&str] = &[
    "Like tears in the rain.",
    "Have you ever retired a human by mistake?",
    "It's too bad she won't live. But then again, who does?",
    "The sky above the port was the color of television, tuned to a dead channel.",
    "Your effort to remain what you are is what limits you.",
    "The passion to build has cooled, and the joy of construction has forgotten.",
    "I don't know if it's me or Tyrell's niece.",
    "And can you offer me proof of your existence?",
    "Fear isn't a weakness. It's here to protect you.",
    "It's the code you live by that defines who you are.",
    "Your body can be chrome, but the heart never changes.",
];

static DAEMON_PORT: OnceLock<u16> = OnceLock::new();

/// Puerto del daemon — seteado una única vez desde `main()` (flag `--port`,
/// que `rinthel-boot.sh` pasa leyendo `RINTHEL_DAEMON_PORT` del `.env`).
/// Sin setear todavía (tests, o correr el binario a mano sin boot.sh) cae al
/// 8765 de siempre.
pub fn set_daemon_port(port: u16) {
    let _ = DAEMON_PORT.set(port);
}

fn daemon_port() -> u16 {
    *DAEMON_PORT.get_or_init(|| 8765)
}

pub fn daemon_base() -> String {
    format!("http://127.0.0.1:{}", daemon_port())
}

/// Nombre del header que valida la access policy `service` del daemon
/// (ADR 0003): el control-plane de infra (boot/terminate/reload/install/
/// config/secrets/ws-monitor) lo exige en cada ruta.
const SERVICE_SECRET_HEADER: &str = "X-Rinthel-Service-Secret";

/// El secreto de servicio vigente. Arranca con el del entorno del proceso
/// (`rinthel-boot.sh` lo exporta desde `RINTHEL_SERVICE_SECRET` en `.env`,
/// mismo patrón que `RINTHEL_DAEMON_PORT` -> `--port`, ver `parse_port_arg`
/// en `main.rs`) y cambia solo cuando `POST /secrets/rotate` trae uno nuevo
/// — la TUI no relee el `.env`. Vacío (pre-install) es válido acá: el
/// daemon es quien devuelve 401.
pub(crate) struct ServiceSecret(RwLock<String>);

impl ServiceSecret {
    fn new(secret: String) -> Self {
        Self(RwLock::new(secret))
    }

    fn get(&self) -> String {
        self.0.read().unwrap_or_else(|e| e.into_inner()).clone()
    }

    /// Toma el secreto nuevo si la respuesta lo trae, aunque recrear algún
    /// servicio haya fallado: el daemon ya lo rotó y ya no acepta el viejo.
    pub(crate) fn adopt(&self, result: &RotateResult) {
        if let Some(secret) = &result.service_secret {
            *self.0.write().unwrap_or_else(|e| e.into_inner()) = secret.clone();
        }
    }
}

pub(crate) static SERVICE_SECRET: LazyLock<ServiceSecret> =
    LazyLock::new(|| ServiceSecret::new(std::env::var("RINTHEL_SERVICE_SECRET").unwrap_or_default()));

fn service_secret() -> String {
    SERVICE_SECRET.get()
}

/// `GET /theme` — `service_or_admin` del lado daemon (ADR 0003), así que
/// lleva el mismo secreto que el resto del control-plane.
pub async fn fetch_theme() -> reqwest::Result<Theme> {
    fetch_theme_from(&daemon_base()).await
}

async fn fetch_theme_from(base: &str) -> reqwest::Result<Theme> {
    reqwest::Client::new()
        .get(format!("{base}/theme"))
        .header(SERVICE_SECRET_HEADER, service_secret())
        .send()
        .await?
        .error_for_status()?
        .json()
        .await
}

fn ws_url() -> String {
    format!(
        "ws://127.0.0.1:{}/ws/monitor?token={}",
        daemon_port(),
        service_secret()
    )
}
const HIST_LEN: usize = 60;
/// Columnas por pulsación de `Left`/`Right` sobre el log_tail.
const LOG_SCROLL_STEP: i32 = 8;

/// Eventos que las tareas de fondo empujan hacia el loop principal —
/// mismo patrón que un `Message` en Elm/TEA, adaptado a Rust con un canal.
#[derive(Debug)]
pub enum AppEvent {
    Docker(Vec<DockerContainer>),
    Gpu(GpuSample),
    CpuRam(CpuRamSample),
    Log(String),
    CommandDone(&'static str, CommandResult),
    CommandFailed(&'static str, String),
    /// `phase_status` (ver docs/adr/0001): (label, status).
    PhaseStatus(String, String),
    /// `phase_log`: (kind, message).
    PhaseLog(String, String),
    /// `phase_batch` (ver docs/adr/0001): límite entre tandas de `/reload` —
    /// dispara Datamosh ("boot") o Vignette ("rebuild"). `"shutdown"` nunca
    /// llega (nadie la emite, ver `protocol::PhaseBatch`).
    PhaseBatch(String),
    /// `models_status`: estado parado, no un evento de corrida.
    ModelsStatus(ModelsStatus),
    /// `GET /config` resuelto — disparado al entrar a `ScreenId::Settings`.
    ConfigLoaded(ConfigPayload),
    ConfigLoadFailed(String),
    /// `POST /config` resuelto con `ok: true`.
    ConfigSaved { written: u32, warnings: Vec<String> },
    /// `ok: false` (errores de `RinthelConfig.validate()`) o falla de red —
    /// ambos se muestran igual (lista de líneas de error).
    ConfigSaveFailed(Vec<String>),
}

/// A qué pantalla vuelve la screen de farewell al terminar sus 5s: desde el
/// cierre de una corrida (BOOT/TERMINATE/RELOAD/INSTALL) vuelve al checklist
/// ya cerrado; desde EXIT sale de la app.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum FarewellNext {
    BackToPhaseRunner,
    Quit,
}

/// Qué hacer cuando `App::active_effect` termina — el loop principal no
/// puede bloquearse esperando a un efecto, así que la continuación se
/// guarda como dato en vez de ejecutarse inline al terminar el efecto.
pub enum EffectFollowUp {
    None,
    /// SignalNoise antes de BOOT/RELOAD/TERMINATE/INSTALL — dispara el POST
    /// recién cuando termina.
    StartPhaseRun { name: &'static str, path: &'static str, title: &'static str },
    /// Cierre de BOOT/TERMINATE/RELOAD/INSTALL exitosos: banner al log +
    /// farewell si corresponde (TERMINATE) — recién acá se libera
    /// `command_in_flight`, así que Esc queda bloqueado hasta este punto.
    FinishClosing { banner: String, show_farewell: bool },
}

pub struct Colors {
    pub fg: Color,
    pub accent: Color,
    pub warn: Color,
    pub success: Color,
    pub hot: Color,
    pub dim: Color,
    pub bg: Color,
    /// Resto de la paleta canónica — solo la usan los efectos de transición
    /// (`electric`/`glow`, ej. `ChromaticAberrationEffect`).
    pub electric: Color,
    pub glow: Color,
    /// Paleta "extended" (`theme/palette.py`) — solo la usan los efectos de
    /// transición.
    pub cool: Color,
    pub cool_dim: Color,
    pub hot_dim: Color,
    pub electric_dim: Color,
    pub steel: Color,
    pub steel_dim: Color,
    /// `palette.FRAME_CHARS` — glifos de corrupción/banner compartidos por
    /// varios efectos.
    pub frame_chars: Vec<char>,
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
            electric: hex(&t.canonical.electric),
            glow: hex(&t.canonical.glow),
            cool: hex(&t.extended.cool),
            cool_dim: hex(&t.extended.cool_dim),
            hot_dim: hex(&t.extended.hot_dim),
            electric_dim: hex(&t.extended.electric_dim),
            steel: hex(&t.extended.steel),
            steel_dim: hex(&t.extended.steel_dim),
            frame_chars: t.frame_chars.iter().filter_map(|s| s.chars().next()).collect(),
        }
    }
}

pub struct App {
    pub screen: ScreenId,
    pub menu_selected: usize,
    pub colors: Colors,
    pub containers: Vec<DockerContainer>,
    /// `models_status` en vivo: una línea por Capability y una fila por
    /// managed service, tal como los reporta el daemon.
    pub models_status: ModelsStatus,
    pub gpu: GpuSample,
    pub cpu_ram: CpuRamSample,
    pub cpu_hist: VecDeque<u64>,
    pub ram_hist: VecDeque<u64>,
    pub gpu_hist: VecDeque<u64>,
    pub log_lines: VecDeque<String>,
    /// Offset horizontal (en columnas) del tail de log — `Left`/`Right` lo
    /// mueven en `screens::monitor`/`screens::logs`, ambas comparten
    /// `widgets::log_tail`. Las líneas de llama-server suelen superar el
    /// ancho del panel, así que sin esto quedan truncadas sin forma de
    /// leerlas enteras.
    pub log_scroll_x: u16,
    pub command_in_flight: Option<&'static str>,
    pub last_command_result: Option<(&'static str, CommandResult)>,
    pub last_command_error: Option<String>,
    /// Título de la screen de checklist para la corrida en curso —
    /// "EXECUTE — FAST BOOT" / "SHUTDOWN SEQUENCE".
    pub phase_title: &'static str,
    /// Filas del checklist, en el orden en que llegó su primer evento
    /// `phase_status` — ver doc-comment de `widgets/checklist.rs`.
    pub phase_rows: Vec<(String, String)>,
    /// Log en vivo de la corrida — (kind, message), igual que `phase_log`.
    pub phase_log: VecDeque<(String, String)>,
    pub phase_progress: screens::phase_runner::Progress,
    /// `ScreenId::ExitPrompt` — `Some` mientras se espera la elección de
    /// apagar o no el daemon, consultado cada vuelta del loop igual que
    /// `farewell_timer`.
    pub exit_prompt_timer: Option<ExitPromptTimer>,
    pub farewell_timer: Option<FarewellTimer>,
    pub farewell_next: FarewellNext,
    /// Reveal del mensaje de farewell — se crea junto con `farewell_timer`
    /// (mismo instante de arranque, ver `begin_farewell`), no en `App::new`
    /// (recién sabemos el texto/momento cuando se entra a la screen).
    pub farewell_message: Option<effects::flicker::GlitchReveal>,
    /// Efecto de transición modal en curso — `Some` mientras esté activo, se
    /// dibuja encima de la screen de siempre (ver `effects::GridWidget`) y
    /// consume todo el input salvo `q`.
    pub active_effect: Option<ActiveEffect>,
    pub effect_followup: EffectFollowUp,
    /// Reveal del título del menú — arranca una sola vez al crear `App` (el
    /// menú es la screen inicial y vive todo el proceso, no se remonta).
    pub menu_title: effects::flicker::GlitchReveal,
    pub menu_tagline: effects::tagline::RotatingTagline,
    /// Estado de `ScreenId::Settings` — agrupado en `screens::settings`
    /// (no acá) para que agregar una configuración nueva toque un solo
    /// struct chico en vez de este.
    pub settings: SettingsState,
    should_quit: bool,
}

impl App {
    pub fn new(theme: &Theme) -> Self {
        App {
            screen: ScreenId::Menu,
            menu_selected: screens::first_selectable(),
            colors: Colors::from(theme),
            containers: Vec::new(),
            models_status: ModelsStatus::default(),
            gpu: GpuSample::default(),
            cpu_ram: CpuRamSample::default(),
            cpu_hist: VecDeque::with_capacity(HIST_LEN),
            ram_hist: VecDeque::with_capacity(HIST_LEN),
            gpu_hist: VecDeque::with_capacity(HIST_LEN),
            log_lines: VecDeque::with_capacity(200),
            log_scroll_x: 0,
            command_in_flight: None,
            last_command_result: None,
            last_command_error: None,
            phase_title: "",
            phase_rows: Vec::new(),
            phase_log: VecDeque::new(),
            phase_progress: screens::phase_runner::Progress::default(),
            exit_prompt_timer: None,
            farewell_timer: None,
            farewell_next: FarewellNext::Quit,
            farewell_message: None,
            active_effect: None,
            effect_followup: EffectFollowUp::None,
            menu_title: effects::flicker::GlitchReveal::start(
                "◈ RINTHEL.AI -- NIGHT CITY COMMAND TERMINAL",
                12,
                50,
            ),
            menu_tagline: effects::tagline::RotatingTagline::new(TAGLINES, 6.0, 6, 40),
            settings: SettingsState::default(),
            should_quit: false,
        }
    }

    /// Mueve `log_scroll_x` por `delta` columnas, clampeado a `[0, línea
    /// más larga - 1]` — evita que el slider se vaya más allá del final
    /// real del texto (a diferencia del thumb del `Scrollbar`, que solo
    /// clampea su propio dibujo, no el offset del `Paragraph`).
    fn scroll_log_x(&mut self, delta: i32) {
        let max_len = self.log_lines.iter().map(|l| l.chars().count()).max().unwrap_or(0) as i64;
        let max_scroll = (max_len - 1).max(0);
        let new_val = (self.log_scroll_x as i64 + delta as i64).clamp(0, max_scroll);
        self.log_scroll_x = new_val as u16;
    }

    fn push_hist(hist: &mut VecDeque<u64>, v: u64) {
        if hist.len() == HIST_LEN {
            hist.pop_front();
        }
        hist.push_back(v);
    }

    fn apply(&mut self, ev: AppEvent) {
        self.apply_at(ev, Instant::now());
    }

    fn apply_at(&mut self, ev: AppEvent, now: Instant) {
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
                self.phase_progress.finish(now);
                self.last_command_error = None;
                if name == "boot" || name == "terminate" || name == "reload" || name == "install" || name == "rotate" {
                    // `finish_phase_sequence` decide cuándo se libera
                    // `command_in_flight` — recién al cerrar el efecto de
                    // cierre en un éxito (ver `EffectFollowUp::FinishClosing`),
                    // de una si la secuencia falló.
                    self.finish_phase_sequence(name, &result);
                } else {
                    self.command_in_flight = None;
                }
                self.last_command_result = Some((name, result));
            }
            AppEvent::CommandFailed(name, err) => {
                self.phase_progress.finish(now);
                self.command_in_flight = None;
                // Sin esto un rechazo del POST (401/409) deja el log de
                // PhaseRunner vacío; el menú lo muestra igual en su línea
                // de estado.
                if self.screen == ScreenId::PhaseRunner {
                    self.phase_progress.fail();
                    self.phase_log.push_back(("error".to_string(), format!("{name} falló: {err}")));
                }
                self.last_command_error = Some(format!("{name} falló: {err}"));
            }
            AppEvent::PhaseStatus(label, status) => {
                self.phase_progress.step(label.clone(), &status, now);
                match self.phase_rows.iter_mut().find(|(l, _)| *l == label) {
                    Some(row) => row.1 = status,
                    None => self.phase_rows.push((label, status)),
                }
            }
            AppEvent::PhaseLog(kind, message) => {
                self.phase_progress.observe(now);
                if kind == "error" {
                    self.phase_progress.fail();
                }
                if self.phase_log.len() == 200 {
                    self.phase_log.pop_front();
                }
                self.phase_log.push_back((kind, message));
            }
            AppEvent::PhaseBatch(batch) => {
                self.phase_progress.batch(batch.clone(), now);
                let effect = match batch.as_str() {
                    "boot" => Some(ActiveEffect::Datamosh(effects::DatamoshEffect::new(2.0, 2))),
                    "rebuild" => Some(ActiveEffect::Vignette(effects::VignetteEffect::new(2.0, 2))),
                    _ => None,
                };
                if let Some(effect) = effect {
                    // Sin followup: `phase_status`/`phase_log` de la tanda
                    // que ya está corriendo del lado daemon siguen
                    // llegando y aplicándose (ver loop de `run()`) aunque
                    // la pantalla esté mostrando el efecto encima — al
                    // terminar, el checklist ya está al día solo.
                    self.begin_effect(effect, EffectFollowUp::None);
                }
            }
            AppEvent::ModelsStatus(status) => self.models_status = status,
            AppEvent::ConfigLoaded(payload) => {
                self.settings.payload = Some(payload);
                self.settings.selected_service = 0;
                self.settings.selected_row = 0;
                self.settings.focus = ConfigFocus::Services;
            }
            AppEvent::ConfigLoadFailed(err) => {
                self.settings.status = Some(ConfigSaveStatus::Failed(format!("GET /config falló: {err}")));
            }
            AppEvent::ConfigSaved { written, warnings } => {
                self.settings.save_in_flight = false;
                self.settings.edits.clear();
                let msg = if written == 0 {
                    "nada para guardar — no tocaste ningún valor".to_string()
                } else {
                    format!("guardado ({written} cambio(s)) — aplica en el próximo BOOT/RELOAD")
                };
                let msg = if warnings.is_empty() { msg } else { format!("{msg} — {}", warnings.join("; ")) };
                self.settings.status = Some(ConfigSaveStatus::Saved(msg));
            }
            AppEvent::ConfigSaveFailed(errors) => {
                self.settings.save_in_flight = false;
                self.settings.status = Some(ConfigSaveStatus::Failed(errors.join("; ")));
            }
        }
    }

    /// Al llegar la respuesta bloqueante de `/boot`/`/terminate`/`/reload`/
    /// `/install`, cierra el log de la corrida: mensaje de cierre, un efecto
    /// de transición (`begin_effect`), y recién cuando ese efecto termina el
    /// banner + farewell si corresponde (`EffectFollowUp::FinishClosing`) —
    /// o "secuencia cortada" de una si algo falló (sin efecto).
    fn finish_phase_sequence(&mut self, name: &'static str, result: &CommandResult) {
        match result.results.iter().find(|r| !r.ok) {
            Some(failed) => {
                self.phase_log.push_back((
                    "error".to_string(),
                    format!("secuencia cortada: {}: {}", failed.service, failed.message),
                ));
                self.command_in_flight = None;
            }
            // Sin banner ni efecto: una rotación no cambia qué está arriba.
            None if name == "rotate" => {
                self.phase_log.push_back(("success".to_string(), "Secreto rotado.".to_string()));
                self.command_in_flight = None;
            }
            None => {
                let (done_msg, banner, effect): (&str, &str, ActiveEffect) = match name {
                    "reload" => (
                        "Reboot completo.",
                        "SYSTEM REBOOTED — TODOS LOS SERVICIOS ACTIVOS",
                        ActiveEffect::SyncSweep(effects::SyncSweepEffect::new(1.2)),
                    ),
                    "boot" => (
                        "Secuencia completa.",
                        "TODO EN LINEA — SERVICIOS ACTIVOS",
                        ActiveEffect::ChromaticAberration(effects::ChromaticAberrationEffect::new("SYSTEM ONLINE", 1.0)),
                    ),
                    "install" => (
                        "Setup listo.",
                        "SETUP LISTO — elegí [1] BOOT para levantar todo",
                        ActiveEffect::ChromaticAberration(effects::ChromaticAberrationEffect::new("SETUP LISTO", 1.0)),
                    ),
                    _ => (
                        "Secuencia completa.",
                        "SYSTEM OFFLINE — TODOS LOS SERVICIOS DETENIDOS",
                        ActiveEffect::Afterimage(effects::AfterimageEffect::new("SYSTEM OFFLINE")),
                    ),
                };
                self.phase_log.push_back(("success".to_string(), done_msg.to_string()));
                self.begin_effect(
                    effect,
                    EffectFollowUp::FinishClosing { banner: banner.to_string(), show_farewell: name == "terminate" },
                );
            }
        }
    }

    /// Resuelve `ScreenId::ExitPrompt` — llamado tanto por la elección
    /// explícita (tecla Y/N) como por el timeout (default: apaga). Siempre
    /// sigue a la screen de farewell, nunca la reemplaza.
    fn resolve_exit_prompt(&mut self, shutdown_daemon: bool) {
        self.exit_prompt_timer = None;
        if shutdown_daemon {
            Self::spawn_daemon_stop();
        }
        self.screen = ScreenId::Farewell;
        self.begin_farewell(FarewellNext::Quit);
    }

    /// Apaga el daemon vía `./rinthel-boot.sh --stop` (que ya sabe manejar
    /// pid vivo, poll, y pidfile stale), fire-and-forget: no se espera a que
    /// termine ni se reporta el resultado. Asume cwd = raíz del repo, la
    /// misma asunción que ya documenta `rinthel-boot.sh` (que a su vez
    /// `exec`ea este binario sin hacer `cd`). stdout/stderr a
    /// `Stdio::null()` para no pisar la alternate screen del cliente con los
    /// `echo` del script.
    fn spawn_daemon_stop() {
        let _ = tokio::process::Command::new("./rinthel-boot.sh")
            .arg("--stop")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn();
    }

    /// `FarewellTimer::start()` + el `GlitchLabel(MESSAGE, frames=14)` que
    /// lo acompaña — mismo instante de arranque para ambos, así el reveal
    /// coincide con el inicio real de los 5s de farewell.
    fn begin_farewell(&mut self, next: FarewellNext) {
        self.farewell_timer = Some(FarewellTimer::start());
        self.farewell_message = Some(effects::flicker::GlitchReveal::start(screens::farewell::MESSAGE, 14, 60));
        self.farewell_next = next;
    }

    /// `SignalNoiseEffect(1, 3, 20)` antes de cualquier transición real,
    /// dada por `followup`.
    fn begin_pre_transition(&mut self, followup: EffectFollowUp) {
        self.begin_effect(ActiveEffect::SignalNoise(effects::SignalNoiseEffect::new(1.0, 3, 20)), followup);
    }

    fn begin_effect(&mut self, effect: ActiveEffect, followup: EffectFollowUp) {
        self.active_effect = Some(effect);
        self.effect_followup = followup;
    }

    /// Se llama cuando `active_effect` termina (ver loop de `run()`).
    fn run_effect_followup(&mut self, tx: &mpsc::UnboundedSender<AppEvent>) {
        match std::mem::replace(&mut self.effect_followup, EffectFollowUp::None) {
            EffectFollowUp::None => {}
            EffectFollowUp::StartPhaseRun { name, path, title } => self.start_phase_run(name, path, title, tx),
            EffectFollowUp::FinishClosing { banner, show_farewell } => {
                self.phase_log.push_back(("success".to_string(), format!("◈ {banner}")));
                if show_farewell {
                    self.screen = ScreenId::Farewell;
                    self.begin_farewell(FarewellNext::BackToPhaseRunner);
                }
                // Recién acá — Esc queda bloqueado (`screens::phase_runner::done`)
                // mientras el banner de cierre todavía no se escribió.
                self.command_in_flight = None;
            }
        }
    }

    /// La semántica de cada opción de menú vive en `screens::MENU_ENTRIES`,
    /// no acá.
    fn dispatch_menu_action(&mut self, tx: &mpsc::UnboundedSender<AppEvent>) {
        // `Divider` no es seleccionable (next_selectable/prev_selectable ya
        // lo garantizan), pero el match no puede probarlo — si algún día
        // deja de ser cierto, mejor no-op que panic.
        let Some(entry) = screens::MENU_ENTRIES[self.menu_selected].as_entry() else { return };
        match entry.action {
            MenuAction::Navigate(id) => self.screen = id,
            // SignalNoise (1s) ANTES de cambiar de pantalla y disparar el
            // POST — Navigate/Settings (Monitor/Logs/Configurar) no lo
            // llevan.
            MenuAction::Boot => self.begin_pre_transition(EffectFollowUp::StartPhaseRun {
                name: "boot",
                path: "/boot",
                title: "EXECUTE — FAST BOOT",
            }),
            MenuAction::Reload => self.begin_pre_transition(EffectFollowUp::StartPhaseRun {
                name: "reload",
                path: "/reload",
                title: "SYSTEM REBOOT",
            }),
            MenuAction::Terminate => self.begin_pre_transition(EffectFollowUp::StartPhaseRun {
                name: "terminate",
                path: "/terminate",
                title: "SHUTDOWN SEQUENCE",
            }),
            MenuAction::Install => self.begin_pre_transition(EffectFollowUp::StartPhaseRun {
                name: "install",
                path: "/install",
                title: "INSTALL — SETUP INICIAL",
            }),
            MenuAction::Settings => {
                self.screen = ScreenId::Settings;
                self.settings.payload = None;
                self.settings.edits.clear();
                self.settings.editing = None;
                self.settings.status = None;
                self.settings.save_in_flight = false;
                tokio::spawn(fetch_config(tx.clone()));
            }
            // EXIT pasa por el prompt de apagado del daemon antes de la
            // screen de farewell — ver doc-comment de `screens::exit_prompt`.
            // Sin SignalNoise antes.
            MenuAction::Quit => {
                self.screen = ScreenId::ExitPrompt;
                self.exit_prompt_timer = Some(ExitPromptTimer::start());
            }
        }
    }

    /// Boot/Terminate/Reload/Install comparten el mismo arranque: limpiar el
    /// checklist/log de la corrida anterior, pasar a `ScreenId::PhaseRunner`
    /// y disparar el POST bloqueante en una tarea aparte.
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
        self.phase_progress.start(Instant::now(), name == "reload");
        self.screen = ScreenId::PhaseRunner;
        self.command_in_flight = Some(name);
        tokio::spawn(run_command(name, path, tx.clone()));
    }

    /// Rotar un secreto corre como una secuencia más en
    /// `ScreenId::PhaseRunner`: el checklist muestra en vivo lo que se
    /// recrea por la rotación, si algo.
    pub(crate) fn start_rotation(&mut self, key: SecretKey, tx: &mpsc::UnboundedSender<AppEvent>) {
        self.phase_title = " ◈ ROTAR SECRETO ";
        self.phase_rows.clear();
        self.phase_log.clear();
        self.phase_progress.start(Instant::now(), false);
        self.screen = ScreenId::PhaseRunner;
        self.command_in_flight = Some("rotate");
        tokio::spawn(rotate_secret(key, tx.clone()));
    }

    /// Loop principal: terminal alternate-screen, tick de eventos + polling
    /// de teclado, hasta `q`/SALIR.
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
                let now = Instant::now();
                let size = terminal.size()?;
                let (width, height) = (size.width as usize, size.height as usize);

                // Rotación de frases del menú — corre siempre en segundo
                // plano; el menú no se remonta cada vez que se vuelve a él.
                self.menu_tagline.advance(now);

                if let Some(effect) = &mut self.active_effect {
                    effect.advance(now, width, height, &self.colors);
                }
                if self.active_effect.as_ref().is_some_and(|e| e.is_done(now)) {
                    self.active_effect = None;
                    self.run_effect_followup(&tx);
                }

                terminal.draw(|f| draw(f, &self))?;

                while let Ok(ev) = rx.try_recv() {
                    self.apply(ev);
                }

                // Sin elección a tiempo, apaga todo por default (a prueba
                // de olvidos) — mismo patrón de "consultar el timer cada
                // vuelta" que `farewell_timer`, abajo.
                if self.screen == ScreenId::ExitPrompt
                    && self.exit_prompt_timer.as_ref().is_some_and(|t| t.is_done())
                {
                    self.resolve_exit_prompt(true);
                }

                // Sin callback de timer disponible acá, así que se consulta
                // el estado del farewell cada vuelta del loop en vez de
                // agendar uno.
                if self.screen == ScreenId::Farewell {
                    if let Some(timer) = &self.farewell_timer {
                        if timer.is_done() {
                            self.farewell_timer = None;
                            self.farewell_message = None;
                            match self.farewell_next {
                                FarewellNext::Quit => self.should_quit = true,
                                FarewellNext::BackToPhaseRunner => self.screen = ScreenId::PhaseRunner,
                            }
                        }
                    }
                }

                if event::poll(Duration::from_millis(80))? {
                    if let Event::Key(key) = event::read()? {
                        // Mientras un efecto de transición está en curso
                        // consume toda la pantalla (ver `draw`) y bloquea el
                        // input salvo `q`.
                        if self.active_effect.is_some() {
                            if key.code == KeyCode::Char('q') {
                                self.should_quit = true;
                            }
                        } else if !screens::handle_key(self.screen, &mut self, key.code, &tx) {
                            // `screens::handle_key` ya resolvió la tecla si la
                            // screen actual tiene su propio manejo dedicado
                            // (hoy: Settings) — acá abajo solo lo genérico,
                            // compartido o sin sub-estado propio.
                            match (self.screen, key.code) {
                                // Logs bindea q/Escape a "volver", no a
                                // "salir" — tiene que resolverse antes del
                                // catch-all de abajo.
                                (ScreenId::Logs, KeyCode::Char('q') | KeyCode::Esc) => {
                                    self.screen = ScreenId::Menu;
                                }
                                // 'q' en ExitPrompt cae al catch-all de abajo
                                // (sale sin apagar el daemon, sin pasar por
                                // esta elección) — no se lo especial-casó,
                                // mismo criterio que el resto del cliente.
                                (ScreenId::ExitPrompt, KeyCode::Char('y') | KeyCode::Enter) => {
                                    self.resolve_exit_prompt(true);
                                }
                                (ScreenId::ExitPrompt, KeyCode::Char('n')) => {
                                    self.resolve_exit_prompt(false);
                                }
                                (_, KeyCode::Char('q')) => self.should_quit = true,
                                (ScreenId::PhaseRunner, code) if self.phase_progress.handle_key(code) => {}
                                (ScreenId::Menu, KeyCode::Up) => {
                                    self.menu_selected = screens::prev_selectable(self.menu_selected);
                                }
                                (ScreenId::Menu, KeyCode::Down) => {
                                    self.menu_selected = screens::next_selectable(self.menu_selected);
                                }
                                (ScreenId::Menu, KeyCode::Enter) => self.dispatch_menu_action(&tx),
                                (ScreenId::Monitor, KeyCode::Esc) => self.screen = ScreenId::Menu,
                                // Slider horizontal del log_tail — comparten
                                // offset ambas screens (mismo `log_scroll_x`,
                                // mismo `VecDeque` de líneas) porque
                                // `widgets::log_tail` es el mismo widget
                                // montado en las dos.
                                (ScreenId::Logs | ScreenId::Monitor, KeyCode::Left) => {
                                    self.scroll_log_x(-LOG_SCROLL_STEP);
                                }
                                (ScreenId::Logs | ScreenId::Monitor, KeyCode::Right) => {
                                    self.scroll_log_x(LOG_SCROLL_STEP);
                                }
                                (ScreenId::Logs | ScreenId::Monitor, KeyCode::Home) => {
                                    self.log_scroll_x = 0;
                                }
                                (ScreenId::Logs | ScreenId::Monitor, KeyCode::End) => {
                                    self.scroll_log_x(i32::MAX);
                                }
                                // PhaseRunner bloquea "volver" hasta terminar
                                // — acá eso es "no hay POST en vuelo".
                                (ScreenId::PhaseRunner, KeyCode::Esc) if screens::phase_runner::done(&self) => {
                                    self.screen = ScreenId::Menu;
                                }
                                _ => {}
                            }
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
    // El efecto se dibuja SOBRE la screen de siempre, sin borrarla —
    // `GridWidget` deja pasar las celdas que no tocó.
    if let Some(grid) = app.active_effect.as_ref().and_then(|e| e.grid()) {
        f.render_widget(effects::GridWidget(grid), f.area());
    }
}

/// Un sobre de `/ws/monitor` a su `AppEvent`, por su tag. Un tag que el
/// cliente no conoce, o un `data` que no matchea, se descarta.
fn decode(env: Envelope) -> Option<AppEvent> {
    match env.kind.as_str() {
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
        "models_status" => serde_json::from_value::<ModelsStatus>(env.data).ok().map(AppEvent::ModelsStatus),
        "phase_batch" => serde_json::from_value::<protocol::PhaseBatch>(env.data)
            .ok()
            .map(|b| AppEvent::PhaseBatch(b.batch)),
        _ => None,
    }
}

async fn ws_task(tx: mpsc::UnboundedSender<AppEvent>) {
    loop {
        let conn = tokio_tungstenite::connect_async(ws_url()).await;
        let Ok((stream, _)) = conn else {
            tokio::time::sleep(Duration::from_secs(2)).await;
            continue;
        };
        let (_write, mut read) = stream.split();
        while let Some(Ok(msg)) = read.next().await {
            let tokio_tungstenite::tungstenite::Message::Text(text) = msg else { continue };
            let Ok(env) = serde_json::from_str::<Envelope>(&text) else { continue };
            let ev = decode(env);
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

#[derive(serde::Deserialize)]
struct ErrorDetail {
    detail: String,
}

/// Convierte una respuesta HTTP no-2xx en un mensaje legible en vez de
/// dejar que `.json::<T>()` la trate como error de deserialización
/// genérico. La access policy `service` del daemon devuelve 401 con body
/// `{"detail": "..."}` cuando `RINTHEL_SERVICE_SECRET` no matchea — antes
/// eso fallaba a deserializar como `CommandResult`/`ConfigPayload`/
/// `ConfigSaveResult` y el mensaje que llegaba a la UI era un error de
/// parseo de serde_json, sin indicar la causa real.
async fn parse_daemon_response<T: serde::de::DeserializeOwned>(resp: reqwest::Response) -> Result<T, String> {
    let status = resp.status();
    if status.is_success() {
        return resp.json::<T>().await.map_err(|e| e.to_string());
    }
    let body = resp.text().await.unwrap_or_default();
    let reason = serde_json::from_str::<ErrorDetail>(&body).map(|e| e.detail).unwrap_or(body);
    if status == reqwest::StatusCode::UNAUTHORIZED {
        Err(format!("secreto de servicio inválido — revisá .env ({reason})"))
    } else {
        Err(format!("{status}: {reason}"))
    }
}

async fn run_command(name: &'static str, path: &str, tx: mpsc::UnboundedSender<AppEvent>) {
    let url = format!("{}{path}", daemon_base());
    match reqwest::Client::new().post(&url).header(SERVICE_SECRET_HEADER, service_secret()).send().await {
        Ok(resp) => match parse_daemon_response::<CommandResult>(resp).await {
            Ok(result) => {
                let _ = tx.send(AppEvent::CommandDone(name, result));
            }
            Err(e) => {
                let _ = tx.send(AppEvent::CommandFailed(name, e));
            }
        },
        Err(e) => {
            let _ = tx.send(AppEvent::CommandFailed(name, e.to_string()));
        }
    }
}

/// `POST /secrets/rotate` — el secreto nuevo (si vino) se adopta antes de
/// mirar si algo falló al recrearse: el daemon ya no acepta el viejo.
async fn rotate_secret(key: SecretKey, tx: mpsc::UnboundedSender<AppEvent>) {
    let ev = match reqwest::Client::new()
        .post(format!("{}/secrets/rotate", daemon_base()))
        .header(SERVICE_SECRET_HEADER, service_secret())
        .json(&serde_json::json!({ "key": key.env() }))
        .send()
        .await
    {
        Ok(resp) => match parse_daemon_response::<RotateResult>(resp).await {
            Ok(result) => {
                SERVICE_SECRET.adopt(&result);
                AppEvent::CommandDone("rotate", CommandResult { results: result.results })
            }
            Err(e) => AppEvent::CommandFailed("rotate", e),
        },
        Err(e) => AppEvent::CommandFailed("rotate", e.to_string()),
    };
    let _ = tx.send(ev);
}

/// `GET /config` — disparado al entrar a `ScreenId::Settings`, mismo
/// trigger-on-entry que el resto de las pantallas que piden datos.
async fn fetch_config(tx: mpsc::UnboundedSender<AppEvent>) {
    let ev = match reqwest::Client::new()
        .get(format!("{}/config", daemon_base()))
        .header(SERVICE_SECRET_HEADER, service_secret())
        .send()
        .await
    {
        Ok(resp) => match parse_daemon_response::<ConfigPayload>(resp).await {
            Ok(payload) => AppEvent::ConfigLoaded(payload),
            Err(e) => AppEvent::ConfigLoadFailed(e),
        },
        Err(e) => AppEvent::ConfigLoadFailed(e.to_string()),
    };
    let _ = tx.send(ev);
}

/// `POST /config` con el dict de overrides tocados en esta sesión de
/// settings (mismo shape que `config.diff_overrides` del lado daemon,
/// que hace el filtrado real). `ok: false` (validación) y falla de red
/// terminan ambas en `ConfigSaveFailed`, mostradas igual (líneas de error).
pub(crate) async fn save_config(overrides: HashMap<String, String>, tx: mpsc::UnboundedSender<AppEvent>) {
    let body = serde_json::json!({ "overrides": overrides });
    let ev = match reqwest::Client::new()
        .post(format!("{}/config", daemon_base()))
        .header(SERVICE_SECRET_HEADER, service_secret())
        .json(&body)
        .send()
        .await
    {
        Ok(resp) => match parse_daemon_response::<ConfigSaveResult>(resp).await {
            Ok(result) if result.ok => AppEvent::ConfigSaved { written: result.written, warnings: result.warnings },
            Ok(result) => AppEvent::ConfigSaveFailed(result.errors),
            Err(e) => AppEvent::ConfigSaveFailed(vec![e]),
        },
        Err(e) => AppEvent::ConfigSaveFailed(vec![e.to_string()]),
    };
    let _ = tx.send(ev);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{ServiceOutcome, ServiceState};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    #[test]
    fn reload_shows_current_activity_after_many_events() {
        let theme = serde_json::from_str(include_str!("../../tests/protocol_fixtures/theme.json")).unwrap();
        let mut app = App::new(&theme);
        app.screen = ScreenId::PhaseRunner;
        app.phase_title = "RELOAD";
        app.command_in_flight = Some("reload");
        app.apply(AppEvent::PhaseBatch("rebuild".into()));
        app.apply(AppEvent::PhaseStatus("Construir Deck".into(), "running".into()));
        for i in 0..50 {
            app.apply(AppEvent::PhaseLog("info".into(), format!("build layer {i}")));
        }
        let mut terminal = Terminal::new(ratatui::backend::TestBackend::new(100, 15)).unwrap();
        terminal.draw(|f| screens::phase_runner::draw(f, &app)).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("Fase: rebuild"), "{text}");
        assert!(text.contains("Paso: Construir Deck"), "{text}");
        assert!(text.contains("Transcurrido:"), "{text}");
        assert!(text.contains("Última actividad:"), "{text}");
        assert!(text.contains("build layer 49"), "{text}");
        assert!(text.contains("Tab: detalle"), "{text}");
    }

    #[test]
    fn reload_detail_can_expand_and_show_multiline_tail() {
        let theme = serde_json::from_str(include_str!("../../tests/protocol_fixtures/theme.json")).unwrap();
        let mut app = App::new(&theme);
        app.phase_title = "RELOAD";
        app.apply(AppEvent::PhaseLog("info".into(), (0..30).map(|i| format!("layer {i}\n")).collect()));
        assert!(app.phase_progress.handle_key(KeyCode::Tab));
        let mut terminal = Terminal::new(ratatui::backend::TestBackend::new(100, 12)).unwrap();
        terminal.draw(|f| screens::phase_runner::draw(f, &app)).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("layer 29"), "{text}");
        assert!(text.contains("layer 28"), "{text}");
        assert!(!text.contains("layer 0 "), "{text}");
        app.phase_progress.handle_key(KeyCode::Tab);
        terminal.draw(|f| screens::phase_runner::draw(f, &app)).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("layer 29"), "{text}");
        assert!(!text.contains("layer 28"), "{text}");
    }

    #[test]
    fn failed_phase_expands_and_wraps_long_error_in_full() {
        let theme = serde_json::from_str(include_str!("../../tests/protocol_fixtures/theme.json")).unwrap();
        let mut app = App::new(&theme);
        app.phase_title = "RELOAD";
        app.phase_progress.start(Instant::now(), true);
        let words: Vec<String> = (0..30).map(|i| format!("w{i:03}")).collect();
        app.apply(AppEvent::PhaseLog("error".into(), format!("migracion fallo: {}", words.join(" "))));
        let mut terminal = Terminal::new(ratatui::backend::TestBackend::new(60, 15)).unwrap();
        terminal.draw(|f| screens::phase_runner::draw(f, &app)).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        for w in [&words[0], &words[14], &words[29]] {
            assert!(text.contains(w.as_str()), "{w} missing: {text}");
        }
        // Left/Right/Home still handled (no-ops while wrapped).
        assert!(app.phase_progress.handle_key(KeyCode::Right));
        assert!(app.phase_progress.handle_key(KeyCode::Home));
    }

    #[test]
    fn healthy_collapsed_phase_stays_one_line_while_error_does_not_leak() {
        let theme = serde_json::from_str(include_str!("../../tests/protocol_fixtures/theme.json")).unwrap();
        let mut app = App::new(&theme);
        app.phase_title = "RELOAD";
        app.phase_progress.start(Instant::now(), true);
        app.apply(AppEvent::PhaseLog("info".into(), "uno".into()));
        app.apply(AppEvent::PhaseLog("info".into(), "dos".into()));
        let mut terminal = Terminal::new(ratatui::backend::TestBackend::new(60, 15)).unwrap();
        terminal.draw(|f| screens::phase_runner::draw(f, &app)).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("dos") && !text.contains("uno"), "{text}");
    }

    #[test]
    fn reload_timer_advances_without_events_and_stops_on_failure() {
        let theme = serde_json::from_str(include_str!("../../tests/protocol_fixtures/theme.json")).unwrap();
        let mut app = App::new(&theme);
        let start = Instant::now();
        app.phase_progress.start(start, true);
        let mut initial = Terminal::new(ratatui::backend::TestBackend::new(100, 15)).unwrap();
        initial.draw(|f| screens::phase_runner::draw_at(f, &app, start)).unwrap();
        let text: String = initial.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("Fase: shutdown"), "{text}");
        app.apply_at(AppEvent::PhaseBatch("boot".into()), start);
        app.apply_at(AppEvent::PhaseStatus("Esperar Understory".into(), "running".into()), start);
        app.apply_at(AppEvent::PhaseLog("info".into(), "Esperando conexión".into()), start + Duration::from_secs(10));
        let mut terminal = Terminal::new(ratatui::backend::TestBackend::new(100, 15)).unwrap();
        terminal.draw(|f| screens::phase_runner::draw_at(f, &app, start + Duration::from_secs(90))).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("Transcurrido: 90 s · Última actividad: hace 80 s"), "{text}");
        assert!(text.contains("Paso: Esperar Understory (running)"), "{text}");
        app.apply_at(AppEvent::CommandFailed("reload", "desconectado".into()), start + Duration::from_secs(95));
        terminal.draw(|f| screens::phase_runner::draw_at(f, &app, start + Duration::from_secs(120))).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("Transcurrido: 95 s · Última actividad: hace 110 s"), "{text}");
        app.phase_progress.start(start + Duration::from_secs(120), true);
        terminal.draw(|f| screens::phase_runner::draw_at(f, &app, start + Duration::from_secs(122))).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("Transcurrido: 2 s · Última actividad: sin eventos"), "{text}");
        assert!(text.contains("Paso: esperando progreso"), "{text}");
    }

    #[test]
    fn reload_success_freezes_duration_and_keeps_completion_visible() {
        let theme = serde_json::from_str(include_str!("../../tests/protocol_fixtures/theme.json")).unwrap();
        let mut app = App::new(&theme);
        let start = Instant::now();
        app.phase_progress.start(start, true);
        app.apply_at(AppEvent::PhaseBatch("rebuild".into()), start);
        app.apply_at(AppEvent::PhaseStatus("Construir Deck".into(), "done".into()), start + Duration::from_secs(25));
        app.apply_at(AppEvent::CommandDone("reload", CommandResult { results: vec![] }), start + Duration::from_secs(30));
        let mut terminal = Terminal::new(ratatui::backend::TestBackend::new(100, 15)).unwrap();
        terminal.draw(|f| screens::phase_runner::draw_at(f, &app, start + Duration::from_secs(60))).unwrap();
        let text: String = terminal.backend().buffer().content.iter().map(|c| c.symbol()).collect();
        assert!(text.contains("Transcurrido: 30 s · Última actividad: hace 35 s"), "{text}");
        assert!(text.contains("Construir Deck (done)"), "{text}");
        assert!(text.contains("Reboot completo."), "{text}");
    }

    /// Sirve una única respuesta HTTP/1.1 cruda en `127.0.0.1:0` y devuelve
    /// su base URL — un servidor real en loopback, no un `reqwest::Response`
    /// armado a mano, para que el test ejercite el parseo real de `reqwest`,
    /// no una suposición sobre su forma.
    async fn serve_once(status_line: &'static str, body: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut buf = [0u8; 1024];
            let _ = socket.read(&mut buf).await; // descarta el request, no hace falta parsearlo
            let response = format!(
                "{status_line}\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
                body.len()
            );
            let _ = socket.write_all(response.as_bytes()).await;
            let _ = socket.shutdown().await;
        });
        format!("http://{addr}")
    }

    fn rotated(ok: bool, service_secret: Option<&str>) -> RotateResult {
        RotateResult {
            results: vec![ServiceOutcome { service: "deck".into(), ok, message: String::new() }],
            service_secret: service_secret.map(String::from),
        }
    }

    fn envelope(json: &str) -> Envelope {
        serde_json::from_str(json).unwrap()
    }

    fn models_fixture() -> Envelope {
        envelope(include_str!("../../tests/protocol_fixtures/models_status.json"))
    }

    /// La screen de monitor de `app`, una línea de texto por fila.
    fn monitor_screen(app: &App, width: u16) -> String {
        let mut terminal = ratatui::Terminal::new(ratatui::backend::TestBackend::new(width, 40)).unwrap();
        terminal.draw(|f| screens::monitor::draw(f, app)).unwrap();
        terminal
            .backend()
            .buffer()
            .content()
            .chunks(width as usize)
            .map(|row| row.iter().map(|cell| cell.symbol()).collect::<String>() + "\n")
            .collect()
    }

    #[test]
    fn decode_turns_models_status_into_its_event() {
        let Some(AppEvent::ModelsStatus(status)) = decode(models_fixture()) else {
            panic!("no decodificó models_status")
        };

        assert_eq!(status.capabilities[0].model.as_deref(), Some("test-model"));
        assert_eq!(status.capabilities[0].state, ServiceState::Ready);
        assert_eq!(status.services[0].name, "Understory");
    }

    #[test]
    fn decode_ignores_the_retired_llama_status() {
        assert!(decode(envelope(r#"{"type": "llama_status", "data": {"ready": true}}"#)).is_none());
    }

    #[test]
    fn the_monitor_screen_paints_one_line_per_capability() {
        let mut app = app();
        app.apply(decode(envelope(
            r#"{"type": "models_status", "data": {"capabilities": [
                {"capability": "llm", "model": "qwen", "state": "ready", "error": null},
                {"capability": "stt", "model": null, "state": "off", "error": null},
                {"capability": "tts", "model": "voz", "state": "off", "error": "Local model activo desconocido: voz"}
            ], "services": []}}"#,
        ))
        .unwrap());

        let screen = monitor_screen(&app, 120);

        for expected in ["llm · qwen · listo", "stt · — · apagado", "tts · voz · apagado", "desconocido: voz"] {
            assert!(screen.contains(expected), "falta {expected:?} en:\n{screen}");
        }
        assert!(!screen.contains("llama-server "), "el badge de llama-server se retiró:\n{screen}");
    }

    #[test]
    fn the_services_panel_shows_only_what_the_daemon_reports_in_name_order() {
        let mut app = app();
        app.apply(decode(envelope(
            r#"{"type": "models_status", "data": {"capabilities": [], "services": [
                {"name": "Understory", "state": "down"},
                {"name": "Deck", "state": "ready"}
            ]}}"#,
        ))
        .unwrap());

        let screen = monitor_screen(&app, 120);

        let deck = screen.find("Deck ONLINE").unwrap_or_else(|| panic!("falta Deck ONLINE en:\n{screen}"));
        let understory =
            screen.find("Understory OFFLINE").unwrap_or_else(|| panic!("falta Understory OFFLINE en:\n{screen}"));
        assert!(deck < understory, "{screen}");
        assert!(!screen.contains("hostexecd"), "{screen}");
    }

    #[test]
    fn the_services_panel_is_empty_until_the_daemon_reports() {
        let screen = monitor_screen(&app(), 120);

        assert!(!screen.contains("ONLINE") && !screen.contains("OFFLINE"), "{screen}");
    }

    #[test]
    fn service_secret_adopts_the_rotated_one_even_if_a_recreation_failed() {
        let secret = ServiceSecret::new("viejo".into());

        secret.adopt(&rotated(false, Some("nuevo")));

        assert_eq!(secret.get(), "nuevo");
    }

    #[test]
    fn service_secret_is_kept_when_the_response_brings_none() {
        let secret = ServiceSecret::new("viejo".into());

        secret.adopt(&rotated(true, None));

        assert_eq!(secret.get(), "viejo");
    }

    #[tokio::test]
    async fn parse_daemon_response_ok_on_2xx() {
        let base = serve_once("HTTP/1.1 200 OK", r#"{"results":[]}"#).await;
        let resp = reqwest::Client::new().get(&base).send().await.unwrap();

        let result = parse_daemon_response::<CommandResult>(resp).await.unwrap();

        assert!(result.results.is_empty());
    }

    #[tokio::test]
    async fn parse_daemon_response_reports_invalid_secret_on_401() {
        // Mismo body que devuelve la access policy `service` del daemon real
        // (ADR 0003) cuando `RINTHEL_SERVICE_SECRET` no matchea.
        let base = serve_once(
            "HTTP/1.1 401 Unauthorized",
            r#"{"detail":"invalid or missing service secret"}"#,
        )
        .await;
        let resp = reqwest::Client::new().get(&base).send().await.unwrap();

        let err = parse_daemon_response::<CommandResult>(resp).await.unwrap_err();

        // Regresión: un cuerpo de error del daemon debe llegar con su causa,
        // no como error de deserialización genérico de `serde_json`.
        assert!(err.contains("secreto de servicio inválido"), "{err}");
        assert!(err.contains("invalid or missing service secret"), "{err}");
    }

    #[tokio::test]
    async fn parse_daemon_response_reports_status_and_reason_on_other_errors() {
        let base = serve_once("HTTP/1.1 500 Internal Server Error", r#"{"detail":"boom"}"#).await;
        let resp = reqwest::Client::new().get(&base).send().await.unwrap();

        let err = parse_daemon_response::<CommandResult>(resp).await.unwrap_err();

        assert_eq!(err, "500 Internal Server Error: boom");
    }

    /// Como `serve_once`, y además devuelve el pedido crudo que recibió.
    async fn serve_capturing(
        status_line: &'static str,
        body: &'static str,
    ) -> (String, tokio::sync::oneshot::Receiver<String>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let (sent, received) = tokio::sync::oneshot::channel();
        tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut buf = vec![0u8; 8192];
            let n = socket.read(&mut buf).await.unwrap_or(0);
            let _ = sent.send(String::from_utf8_lossy(&buf[..n]).to_lowercase());
            let response = format!(
                "{status_line}\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
                body.len()
            );
            let _ = socket.write_all(response.as_bytes()).await;
            let _ = socket.shutdown().await;
        });
        (format!("http://{addr}"), received)
    }

    fn app() -> App {
        App::new(&serde_json::from_str(include_str!("../../tests/protocol_fixtures/theme.json")).unwrap())
    }

    #[test]
    fn the_menu_has_the_lifecycle_entries_and_no_providers() {
        let labels: Vec<&str> = screens::MENU_ENTRIES.iter().filter_map(|i| i.as_entry()).map(|e| e.label).collect();

        let mut sorted = labels.clone();
        sorted.sort_unstable();
        assert_eq!(sorted, ["BOOT", "CONFIGURAR", "INSTALL", "LOGS", "MONITOR", "RELOAD", "SALIR", "TERMINATE"]);
    }

    #[tokio::test]
    async fn the_theme_is_read_with_the_service_secret() {
        let (base, received) =
            serve_capturing("HTTP/1.1 200 OK", include_str!("../../tests/protocol_fixtures/theme.json")).await;

        fetch_theme_from(&base).await.unwrap();

        let raw = received.await.unwrap();
        assert!(raw.starts_with("get /theme "), "{raw}");
        assert!(raw.contains("x-rinthel-service-secret:"), "{raw}");
    }

    #[tokio::test]
    async fn run_command_reports_command_failed_on_network_error() {
        // `parse_daemon_response` nunca corre en este caso — el error pasa
        // por la rama `Err(e) => ... e.to_string()` de `run_command` misma,
        // antes de llegar a parsear ninguna respuesta (no hay respuesta).
        // Puerto privilegiado de loopback: nadie escucha ahí. Único test de este módulo que toca `daemon_port()`
        // (`OnceLock`, se puede setear una sola vez por proceso).
        set_daemon_port(1);
        let (tx, mut rx) = mpsc::unbounded_channel();

        run_command("boot", "/boot", tx).await;

        match rx.recv().await {
            Some(AppEvent::CommandFailed(name, _)) => assert_eq!(name, "boot"),
            other => panic!("expected CommandFailed, got {other:?}"),
        }
    }
}
