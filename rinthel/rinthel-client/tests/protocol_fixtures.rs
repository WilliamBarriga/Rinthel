//! Fixture dorada: mismos JSON que `tests/protocol/test_fixtures.py` del
//! lado Python, leídos por path relativo desde `../tests/protocol_fixtures/`
//! (fuente única).

use std::fs;
use std::path::PathBuf;

use rinthel::protocol::{
    CommandResult, ConfigPayload, ConfigSaveResult, CpuRamSample, DockerStatus, Envelope, GpuSample, LogLine,
    ModelsStatus, PhaseBatch, PhaseLog, PhaseStatus, RotateResult, ServiceState, Theme,
};

fn fixture(name: &str) -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../tests/protocol_fixtures")
        .join(name);
    fs::read_to_string(&path).unwrap_or_else(|e| panic!("no pude leer {path:?}: {e}"))
}

#[test]
fn theme_shape() {
    let theme: Theme = serde_json::from_str(&fixture("theme.json")).expect("theme.json no matchea Theme");
    assert!(!theme.canonical.fg.is_empty());
    // `extended`/`frame_chars` los usan los efectos de transición.
    assert!(!theme.extended.cool.is_empty());
    assert!(!theme.frame_chars.is_empty());
}

#[test]
fn docker_status_shape() {
    let env: Envelope = serde_json::from_str(&fixture("docker_status.json")).unwrap();
    assert_eq!(env.kind, "docker_status");
    let status: DockerStatus =
        serde_json::from_value(env.data).expect("docker_status.json no matchea DockerStatus");
    assert!(!status.containers.is_empty());
}

#[test]
fn gpu_sample_shape() {
    let env: Envelope = serde_json::from_str(&fixture("gpu_sample.json")).unwrap();
    assert_eq!(env.kind, "gpu_sample");
    let _: GpuSample = serde_json::from_value(env.data).expect("gpu_sample.json no matchea GpuSample");
}

#[test]
fn cpu_ram_sample_shape() {
    let env: Envelope = serde_json::from_str(&fixture("cpu_ram_sample.json")).unwrap();
    assert_eq!(env.kind, "cpu_ram_sample");
    let _: CpuRamSample =
        serde_json::from_value(env.data).expect("cpu_ram_sample.json no matchea CpuRamSample");
}

#[test]
fn log_line_shape() {
    let env: Envelope = serde_json::from_str(&fixture("log_line.json")).unwrap();
    assert_eq!(env.kind, "log_line");
    let _: LogLine = serde_json::from_value(env.data).expect("log_line.json no matchea LogLine");
}

#[test]
fn models_status_shape() {
    let env: Envelope = serde_json::from_str(&fixture("models_status.json")).unwrap();
    assert_eq!(env.kind, "models_status");
    let status: ModelsStatus =
        serde_json::from_value(env.data).expect("models_status.json no matchea ModelsStatus");
    assert_eq!(status.capabilities[0].capability, "llm");
    assert_eq!(status.capabilities[0].state, ServiceState::Ready);
    assert!(status.capabilities[0].error.is_none());
    // Voice, when active, is one more Capability line.
    let voice: Vec<_> = status.capabilities[1..].iter().map(|c| (c.capability.as_str(), c.state)).collect();
    assert_eq!(voice, [("stt", ServiceState::Ready), ("tts", ServiceState::Down)]);
    assert!(!status.services.is_empty());
}

#[test]
fn phase_status_shape() {
    let env: Envelope = serde_json::from_str(&fixture("phase_status.json")).unwrap();
    assert_eq!(env.kind, "phase_status");
    let _: PhaseStatus = serde_json::from_value(env.data).expect("phase_status.json no matchea PhaseStatus");
}

#[test]
fn phase_log_shape() {
    let env: Envelope = serde_json::from_str(&fixture("phase_log.json")).unwrap();
    assert_eq!(env.kind, "phase_log");
    let _: PhaseLog = serde_json::from_value(env.data).expect("phase_log.json no matchea PhaseLog");
}

#[test]
fn phase_batch_shape() {
    let env: Envelope = serde_json::from_str(&fixture("phase_batch.json")).unwrap();
    assert_eq!(env.kind, "phase_batch");
    let _: PhaseBatch = serde_json::from_value(env.data).expect("phase_batch.json no matchea PhaseBatch");
}

#[test]
fn boot_result_shape() {
    let result: CommandResult =
        serde_json::from_str(&fixture("boot_result.json")).expect("boot_result.json no matchea CommandResult");
    assert!(!result.results.is_empty());
}

#[test]
fn terminate_result_shape() {
    let result: CommandResult = serde_json::from_str(&fixture("terminate_result.json"))
        .expect("terminate_result.json no matchea CommandResult");
    assert!(!result.results.is_empty());
}

#[test]
fn config_payload_shape() {
    let payload: ConfigPayload = serde_json::from_str(&fixture("config_payload.json"))
        .expect("config_payload.json no matchea ConfigPayload");
    assert!(!payload.services.is_empty());
    // llama: campos de al menos 2 grupos distintos (ver screens::settings::detail_rows).
    let llama = payload.services.iter().find(|s| s.attr == "llama").expect("fixture sin llama");
    let groups: std::collections::HashSet<_> = llama.fields.iter().map(|f| f.group.as_str()).collect();
    assert!(groups.len() > 1);
    // Los campos del Validated profile traen su valor; el resto, ninguno.
    assert!(llama.fields.iter().any(|f| f.profile.is_some()));
    assert!(llama.fields.iter().any(|f| f.profile.is_none()));
    // Los del Local model no se configuran acá.
    assert!(llama.fields.iter().all(|f| !f.attr.starts_with("spec_")));
}

#[test]
fn config_save_result_shape() {
    let result: ConfigSaveResult = serde_json::from_str(&fixture("config_save_result.json"))
        .expect("config_save_result.json no matchea ConfigSaveResult");
    assert!(!result.ok);
    assert!(!result.errors.is_empty());
}

#[test]
fn rotate_result_shape() {
    let result: RotateResult =
        serde_json::from_str(&fixture("rotate_result.json")).expect("rotate_result.json no matchea RotateResult");
    assert!(result.service_secret.is_some_and(|s| !s.is_empty()));
}

#[test]
fn rotate_result_without_service_secret() {
    // Rotar RINTHEL_PANEL_SECRET: el daemon omite `service_secret`.
    let result: RotateResult = serde_json::from_str(r#"{"results": []}"#).unwrap();
    assert_eq!(result.service_secret, None);
}
