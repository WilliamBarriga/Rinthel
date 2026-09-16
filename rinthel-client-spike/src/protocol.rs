//! Formas de mensaje del protocolo daemon<->cliente.
//! Espejo a mano de los modelos Pydantic del daemon (sin codegen, decisión
//! del ticket 03 / ADR 0001) — mismo snake_case en ambos lados.

use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct Theme {
    pub canonical: Palette,
    #[allow(dead_code)]
    pub extended: serde_json::Value,
    #[allow(dead_code)]
    pub frame_chars: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct Palette {
    pub fg: String,
    pub accent: String,
    #[allow(dead_code)]
    pub electric: String,
    pub warn: String,
    pub success: String,
    pub hot: String,
    #[allow(dead_code)]
    pub caution: String,
    #[allow(dead_code)]
    pub glow: String,
    pub dim: String,
    pub bg: String,
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
