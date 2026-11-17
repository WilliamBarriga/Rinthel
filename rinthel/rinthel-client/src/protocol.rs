//! Formas de mensaje del protocolo daemon<->cliente.
//! Espejo a mano de los modelos Pydantic del daemon (sin codegen, ver
//! docs/adr/0001) — mismo snake_case en ambos lados.

use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct Theme {
    pub canonical: Palette,
    /// Los efectos de transición usan estos colores además de los 9
    /// canónicos.
    pub extended: ExtendedPalette,
    pub frame_chars: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct Palette {
    pub fg: String,
    pub accent: String,
    pub electric: String,
    pub warn: String,
    pub success: String,
    pub hot: String,
    pub caution: String,
    pub glow: String,
    pub dim: String,
    pub bg: String,
}

/// Paleta "extended" de `theme/palette.py` — no forma parte de los 9 colores
/// canónicos, la usan exclusivamente los efectos de transición.
#[derive(Debug, Deserialize)]
pub struct ExtendedPalette {
    pub cool: String,
    pub cool_dim: String,
    pub hot_dim: String,
    pub electric_dim: String,
    pub steel: String,
    pub steel_dim: String,
    #[allow(dead_code)]
    pub accent_dim: String,
}

/// Envelope `{"type": "...", "data": {...}}` que multiplexa /ws/monitor.
#[derive(Debug, Deserialize)]
pub struct Envelope {
    #[serde(rename = "type")]
    pub kind: String,
    pub data: serde_json::Value,
}

#[derive(Debug, Deserialize, Clone)]
pub struct DockerContainer {
    pub name: String,
    pub state: String,
    #[allow(dead_code)]
    pub ports: String,
    pub status: String,
}

#[derive(Debug, Deserialize)]
pub struct DockerStatus {
    pub containers: Vec<DockerContainer>,
}

#[derive(Debug, Deserialize, Clone, Default)]
pub struct GpuSample {
    pub available: bool,
    pub utilization: Option<f64>,
    pub memory_used: Option<f64>,
    pub memory_total: Option<f64>,
    pub temperature: Option<f64>,
    #[allow(dead_code)]
    pub power_draw: Option<f64>,
}

#[derive(Debug, Deserialize, Clone, Default)]
pub struct CpuRamSample {
    pub cpu_percent: f64,
    pub ram_used_gb: f64,
    pub ram_total_gb: f64,
    pub ram_percent: f64,
}

#[derive(Debug, Deserialize)]
pub struct LogLine {
    pub line: String,
}

/// Sobre `models_status`: estado parado, una muestra cada 2 s. Una línea
/// por Capability que la Instance sirve y una fila por cada otro managed
/// service que corre en su Platform — lo que el daemon no reporta no se
/// pinta.
#[derive(Debug, Deserialize, Clone, Default, PartialEq)]
pub struct ModelsStatus {
    pub capabilities: Vec<CapabilityStatus>,
    pub services: Vec<ServiceStatus>,
}

/// Una Capability (`llm`/`stt`/`tts`): el Local model activo (`None` si no
/// hay), el estado de su servicio y, si el activo no puede correr, por qué.
#[derive(Debug, Deserialize, Clone, PartialEq)]
pub struct CapabilityStatus {
    pub capability: String,
    pub model: Option<String>,
    pub state: ServiceState,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Deserialize, Clone, PartialEq)]
pub struct ServiceStatus {
    pub name: String,
    pub state: ServiceState,
}

/// `ready`: responde; `down`: tendría que correr y no responde; `off`: no
/// hay nada que correr (apagado, o sin Local model usable).
#[derive(Debug, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ServiceState {
    Ready,
    Down,
    Off,
}

#[derive(Debug, Deserialize, Clone)]
pub struct ServiceOutcome {
    pub service: String,
    pub ok: bool,
    pub message: String,
}

#[derive(Debug, Deserialize)]
pub struct CommandResult {
    pub results: Vec<ServiceOutcome>,
}

/// Respuesta de `POST /secrets/rotate`: lo que se recreó por la rotación
/// (vacío mientras ningún servicio gestionado lea el secreto) y, solo si se
/// rotó `RINTHEL_SERVICE_SECRET`, el secreto nuevo — la TUI no relee el
/// `.env`.
#[derive(Debug, Deserialize)]
pub struct RotateResult {
    pub results: Vec<ServiceOutcome>,
    #[serde(default)]
    pub service_secret: Option<String>,
}

/// Sobre `phase_status` (ver docs/adr/0001): un mensaje por cada `PhaseSpec`
/// que corre `lifecycle/executor.py` del lado daemon — granularidad fina, no la
/// agrupación por servicio de la respuesta de `/boot`/`/terminate`.
#[derive(Debug, Deserialize)]
pub struct PhaseStatus {
    pub label: String,
    pub status: String,
}

/// Sobre `phase_log` — un mensaje por cada llamada a `report.*` dentro de
/// una fase (incluye `info`, a diferencia del `message` agregado que sí lo
/// descarta en `ServiceOutcome`).
#[derive(Debug, Deserialize)]
pub struct PhaseLog {
    pub kind: String,
    pub message: String,
}

/// Sobre `phase_batch` (ver docs/adr/0001): marca el límite entre tandas de
/// `/reload` — sin esto el cliente no tiene forma de saber cuándo terminó
/// "shutdown" y empezó "boot", o "boot" y "rebuild" (el daemon corre las 3
/// tandas de un tirón, `phase_status`/`phase_log` solo hablan de fases
/// individuales). Dispara Datamosh/Vignette en el cliente. `"shutdown"` no
/// se emite — nada la escucha (no hay transición antes de la primera tanda).
#[derive(Debug, Deserialize)]
pub struct PhaseBatch {
    pub batch: String,
}

/// Un campo editable de `[N] CONFIGURAR` (ver docs/adr/0001) — `value` viaja
/// como string y `kind` le dice al cliente qué widget pintar ("bool" ->
/// checkbox, el resto -> texto) sin que el cliente conozca los tipos de
/// Python. `group` agrupa visualmente (ver `screens::settings`) — "" para
/// sub-configs con pocos campos que no lo necesitan.
#[derive(Debug, Deserialize, Clone)]
pub struct ConfigField {
    pub attr: String,
    pub env: String,
    pub kind: String,
    pub group: String,
    pub value: String,
    /// El valor del Validated profile de la Platform para un campo de
    /// hardware/cache; `None` en los campos que el perfil no cubre. Si el
    /// valor efectivo difiere, la screen lo marca como override.
    #[serde(default)]
    pub profile: Option<String>,
}

/// Una sub-config de `RinthelConfig` (`llama`/`moe`/`understory`/
/// `deck`/`install`) — `enabled`/`enabled_env` son `None` para las que
/// no tienen ese campo (`moe`/`install`: no son un
/// `LocalProcessService`/`DockerComposeService`, no hay on/off).
#[derive(Debug, Deserialize, Clone)]
pub struct ConfigService {
    pub attr: String,
    pub display_name: String,
    pub enabled: Option<bool>,
    pub enabled_env: Option<String>,
    pub fields: Vec<ConfigField>,
}

/// `GET /config` — shape genérico a propósito: sumar un `Field` nuevo del
/// lado daemon lo hace aparecer acá sin tocar este struct.
#[derive(Debug, Deserialize, Clone)]
pub struct ConfigPayload {
    pub services: Vec<ConfigService>,
}

/// Respuesta de `POST /config` — `errors` viene de `RinthelConfig.validate()`
/// (ConfigError, bloquea el write); `warnings` son los paths-no-existen-
/// todavía de `validate()`, no bloquean (mismo criterio que boot/terminate).
#[derive(Debug, Deserialize)]
pub struct ConfigSaveResult {
    pub ok: bool,
    #[serde(default)]
    pub written: u32,
    #[serde(default)]
    pub warnings: Vec<String>,
    #[serde(default)]
    pub errors: Vec<String>,
}
