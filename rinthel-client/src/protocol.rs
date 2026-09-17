//! Formas de mensaje del protocolo daemon<->cliente.
//! Espejo a mano de los modelos Pydantic del daemon (sin codegen, decisión
//! del ticket 03 / ADR 0001) — mismo snake_case en ambos lados.

use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct Theme {
    pub canonical: Palette,
    /// Sesión 10: los 8 effect_* de `tui/effects/transitions.py` usan estos
    /// colores además de los 9 canónicos — quedaban sin parsear (`dead_code`)
    /// desde que `GET /theme` empezó a servirlos (ticket 03), a propósito
    /// diferido hasta esta sesión.
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
/// canónicos, la usan exclusivamente los efectos de transición (sesión 10).
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

/// Sobre `llama_status` (amendment de docs/adr/0001, sesión 08): estado
/// parado, transmitido en loop mientras haya un cliente conectado — no un
/// evento puntual de una corrida como `phase_status`/`phase_log`. `ready`
/// ya significa "servidor arriba + modelo cargado" (un solo GET contra el
/// mismo `ready_url_of` que usa boot/reload), no hace falta más granularidad.
#[derive(Debug, Deserialize, Clone, Default)]
pub struct LlamaStatus {
    pub ready: bool,
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

/// Sobre `phase_status` (amendment de docs/adr/0001, sesión 05): un mensaje
/// por cada `PhaseSpec` que corre `run_phase_list` del lado daemon — misma
/// granularidad fina que `boot_phases()`/`down_phases()`, no la agrupación
/// por servicio de la respuesta de `/boot`/`/terminate`.
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

/// Sobre `phase_batch` (amendment de docs/adr/0001, sesión 10): marca el
/// límite entre tandas de `/reload` — sin esto el cliente no tiene forma de
/// saber cuándo terminó "shutdown" y empezó "boot", o "boot" y "rebuild"
/// (el daemon corre las 3 tandas de un tirón, `phase_status`/`phase_log`
/// solo hablan de fases individuales). Dispara Datamosh/Vignette en el
/// cliente. `"shutdown"` no se emite — nada la escucha (no hay transición
/// antes de la primera tanda en el original).
#[derive(Debug, Deserialize)]
pub struct PhaseBatch {
    pub batch: String,
}

/// Un campo editable de `[N] CONFIGURAR` (amendment de docs/adr/0001,
/// sesión 09) — `value` viaja como string (mismo criterio que un `Input` de
/// Textual) y `kind` le dice al cliente qué widget pintar ("bool" ->
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
}

/// Una sub-config de `RinthelConfig` (`llama`/`moe`/`understory`/
/// `pithagoras`/`install`) — `enabled`/`enabled_env` son `None` para las que
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

/// `GET /config` — shape genérico a propósito (mismo espíritu "genérico"
/// que ya tenía `rinthel_tui/tui/screens/settings.py`): sumar un `Field`
/// nuevo del lado daemon lo hace aparecer acá sin tocar este struct.
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
