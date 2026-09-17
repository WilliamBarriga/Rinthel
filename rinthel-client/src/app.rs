//! Estado de la app (`App`/`AppEvent`/`Colors`) y el loop principal —
//! separado de `main.rs` en la sesión 00 del porteo (ver
//! .scratch/ratatui-migration/port-issues/00-scaffolding-testing-and-crate-skeleton.md).

use std::collections::{HashMap, VecDeque};
use std::io;
use std::sync::OnceLock;
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
    PhaseLog, PhaseStatus, Theme,
};
use crate::screens::farewell::FarewellTimer;
use crate::screens::settings::{self, DetailRow};
use crate::screens::{self, MenuAction, ScreenId};

/// Puerto de `branding/taglines.py` — solo contenido, ver docstring de ese
/// módulo (mezcla status técnico con líneas de peso narrativo, mismo
/// registro que la cita de Blade Runner del banner).
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
/// que `rinthel-boot.sh` pasa leyendo `RINTHEL_DAEMON_PORT` del `.env`;
/// sesión 11 del port-map). Sin setear todavía (tests, o correr el binario
/// a mano sin boot.sh) cae al 8765 de siempre.
pub fn set_daemon_port(port: u16) {
    let _ = DAEMON_PORT.set(port);
}

fn daemon_port() -> u16 {
    *DAEMON_PORT.get_or_init(|| 8765)
}

pub fn daemon_base() -> String {
    format!("http://127.0.0.1:{}", daemon_port())
}

fn ws_url() -> String {
    format!("ws://127.0.0.1:{}/ws/monitor", daemon_port())
}
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
    /// `phase_batch` (amendment de docs/adr/0001, sesión 10): límite entre
    /// tandas de `/reload` — dispara Datamosh ("boot") o Vignette
    /// ("rebuild"). `"shutdown"` nunca llega (nadie la emite, ver
    /// protocol::PhaseBatch).
    PhaseBatch(String),
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

/// Qué hacer cuando `App::active_effect` termina — reemplaza el `await
/// push_screen_wait(effect); <lo que sigue>` secuencial de Python: acá el
/// efecto y su continuación viven separados (el loop principal no puede
/// bloquearse), así que la continuación se guarda como dato en vez de
/// código que sigue inline.
pub enum EffectFollowUp {
    None,
    /// SignalNoise antes de BOOT/RELOAD/TERMINATE/INSTALL — dispara el POST
    /// recién cuando termina, igual que `menu.py:154-176`.
    StartPhaseRun { name: &'static str, path: &'static str, title: &'static str },
    /// SignalNoise antes de CAPTURE (`menu.py:175-177`).
    StartCapture,
    /// Cierre de BOOT/TERMINATE/RELOAD/INSTALL exitosos: banner al log +
    /// farewell si corresponde (TERMINATE) — recién acá se libera
    /// `command_in_flight` (Esc queda bloqueado hasta este punto, igual que
    /// `_done = True` recién después de `_run_closing` en Python).
    FinishClosing { banner: String, show_farewell: bool },
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
    /// Resto de la paleta canónica — sin uso hasta sesión 10 (efectos de
    /// transición): `electric`/`glow` (`ChromaticAberrationEffect`).
    pub electric: Color,
    pub glow: Color,
    /// Paleta "extended" (`theme/palette.py`) — solo la usan los efectos de
    /// transición (sesión 10).
    pub cool: Color,
    pub cool_dim: Color,
    pub hot_dim: Color,
    pub electric_dim: Color,
    pub steel: Color,
    pub steel_dim: Color,
    /// `palette.FRAME_CHARS` — glifos de corrupción/banner compartidos por
    /// varios efectos (`random.choice(palette.FRAME_CHARS)` en Python).
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
    /// Reveal del mensaje de farewell (`GlitchLabel` en Python) — se crea
    /// junto con `farewell_timer` (mismo instante de arranque, ver
    /// `begin_farewell`), no en `App::new` (recién sabemos el texto/momento
    /// cuando se entra a la screen).
    pub farewell_message: Option<effects::flicker::GlitchReveal>,
    /// Efecto de transición modal en curso (sesión 10) — `Some` mientras
    /// esté activo, se dibuja encima de la screen de siempre (ver
    /// `effects::GridWidget`) y consume todo el input salvo `q`.
    pub active_effect: Option<ActiveEffect>,
    pub effect_followup: EffectFollowUp,
    /// Reveal del título del menú (`GlitchLabel` en Python) — arranca una
    /// sola vez al crear `App` (el menú no tiene "on_mount" propio acá, es
    /// la screen inicial y vive todo el proceso).
    pub menu_title: effects::flicker::GlitchReveal,
    pub menu_tagline: effects::tagline::RotatingTagline,
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
            farewell_message: None,
            active_effect: None,
            effect_followup: EffectFollowUp::None,
            menu_title: effects::flicker::GlitchReveal::start(
                "◈ RINTHEL.AI -- NIGHT CITY COMMAND TERMINAL",
                12,
                50,
            ),
            menu_tagline: effects::tagline::RotatingTagline::new(TAGLINES, 6.0, 6, 40),
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
                self.last_command_error = None;
                if name == "boot" || name == "terminate" || name == "reload" || name == "install" {
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
            AppEvent::PhaseBatch(batch) => {
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
    /// corrida — mensaje de cierre, el `ClosingSequence`/Ripple real de
    /// sesión 10 (`begin_effect`), y recién cuando ese efecto termina el
    /// banner + farewell si corresponde (`EffectFollowUp::FinishClosing`) —
    /// o "secuencia cortada" de una si algo falló (sin efecto, igual que
    /// Python: `_run_closing` nunca se llama si `_run_spec` devolvió
    /// `False`).
    fn finish_phase_sequence(&mut self, name: &'static str, result: &CommandResult) {
        match result.results.iter().find(|r| !r.ok) {
            Some(failed) => {
                self.phase_log.push_back((
                    "error".to_string(),
                    format!("secuencia cortada: {}: {}", failed.service, failed.message),
                ));
                self.command_in_flight = None;
            }
            None => {
                let (done_msg, banner, effect): (&str, &str, ActiveEffect) = match name {
                    // Ripple original retirado (session 10, probando en vivo:
                    // "demasiado largo y feo") — ver doc-comment de
                    // `effects::SyncSweepEffect`.
                    "reload" => (
                        "Reboot completo.",
                        "SYSTEM REBOOTED — TODOS LOS SERVICIOS ACTIVOS",
                        ActiveEffect::SyncSweep(effects::SyncSweepEffect::new(1.2)),
                    ),
                    "boot" => (
                        "Secuencia completa.",
                        "TODO EN LINEA — Understory + Pithagoras activos",
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

    /// `FarewellTimer::start()` + el `GlitchLabel(MESSAGE, frames=14)` que
    /// lo acompaña — mismo instante de arranque para ambos, así el reveal
    /// coincide con el inicio real de los 5s de farewell.
    fn begin_farewell(&mut self, next: FarewellNext) {
        self.farewell_timer = Some(FarewellTimer::start());
        self.farewell_message = Some(effects::flicker::GlitchReveal::start(screens::farewell::MESSAGE, 14, 60));
        self.farewell_next = next;
    }

    /// `SignalNoiseEffect(1, 3, 20)` — mismos parámetros que los 5 call
    /// sites de `menu.py`, siempre seguido de la transición real que dio
    /// `followup`.
    fn begin_pre_transition(&mut self, followup: EffectFollowUp) {
        self.begin_effect(ActiveEffect::SignalNoise(effects::SignalNoiseEffect::new(1.0, 3, 20)), followup);
    }

    fn begin_effect(&mut self, effect: ActiveEffect, followup: EffectFollowUp) {
        self.active_effect = Some(effect);
        self.effect_followup = followup;
    }

    /// Se llama cuando `active_effect` termina (ver loop de `run()`) — puerto
    /// de lo que en Python seguía inline después de un
    /// `await push_screen_wait(effect)`.
    fn run_effect_followup(&mut self, tx: &mpsc::UnboundedSender<AppEvent>) {
        match std::mem::replace(&mut self.effect_followup, EffectFollowUp::None) {
            EffectFollowUp::None => {}
            EffectFollowUp::StartPhaseRun { name, path, title } => self.start_phase_run(name, path, title, tx),
            EffectFollowUp::StartCapture => {
                self.screen = ScreenId::Capture;
                self.command_in_flight = Some("capture");
                tokio::spawn(run_command("capture", "/capture", tx.clone()));
            }
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
            // `menu.py:154-176`: SignalNoise (1s) ANTES de cambiar de
            // pantalla y disparar el POST — no antes de Navigate/Settings
            // (Monitor/Logs/Configurar no lo tienen en Python, confirmado
            // en el ticket de esta sesión).
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
            MenuAction::Capture => self.begin_pre_transition(EffectFollowUp::StartCapture),
            MenuAction::Install => self.begin_pre_transition(EffectFollowUp::StartPhaseRun {
                name: "install",
                path: "/install",
                title: "INSTALL — SETUP INICIAL",
            }),
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
            // igual que TERMINATE (grillado con Tarkark, sesión 05). Sin
            // SignalNoise antes (Python tampoco lo dispara para "exit").
            MenuAction::Quit => {
                self.screen = ScreenId::Farewell;
                self.begin_farewell(FarewellNext::Quit);
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
                let now = Instant::now();
                let size = terminal.size()?;
                let (width, height) = (size.width as usize, size.height as usize);

                // Reveal del título + rotación de frases — corren siempre
                // en segundo plano, como el `set_interval` de Python (el
                // menú no se remonta cada vez que se vuelve a él).
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

                // `FarewellScreen._finish` de Python (set_timer + dismiss()):
                // acá no hay callback, así que se consulta el timer cada
                // vuelta del loop en vez de agendar uno.
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
                        // input salvo `q` — mismo trato que ya tenía
                        // `FarewellScreen` (decisión explícita de Tarkark en
                        // sesión 05, extendida acá al resto de los efectos).
                        if self.active_effect.is_some() {
                            if key.code == KeyCode::Char('q') {
                                self.should_quit = true;
                            }
                        } else {
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
    // `TransitionEffect` es un `ModalScreen` con `background: $bg 0%` en
    // Python: se apila SOBRE lo que ya está montado, sin borrarlo — acá es
    // dibujar la screen de siempre y superponer la grilla del efecto
    // encima (`GridWidget` deja pasar las celdas que no tocó).
    if let Some(grid) = app.active_effect.as_ref().and_then(|e| e.grid()) {
        f.render_widget(effects::GridWidget(grid), f.area());
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
                "phase_batch" => serde_json::from_value::<protocol::PhaseBatch>(env.data)
                    .ok()
                    .map(|b| AppEvent::PhaseBatch(b.batch)),
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
    let url = format!("{}{path}", daemon_base());
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
    let ev = match reqwest::get(format!("{}/config", daemon_base())).await {
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
    let ev = match reqwest::Client::new().post(format!("{}/config", daemon_base())).json(&body).send().await {
        Ok(resp) => match resp.json::<ConfigSaveResult>().await {
            Ok(result) if result.ok => AppEvent::ConfigSaved { written: result.written, warnings: result.warnings },
            Ok(result) => AppEvent::ConfigSaveFailed(result.errors),
            Err(e) => AppEvent::ConfigSaveFailed(vec![e.to_string()]),
        },
        Err(e) => AppEvent::ConfigSaveFailed(vec![e.to_string()]),
    };
    let _ = tx.send(ev);
}
