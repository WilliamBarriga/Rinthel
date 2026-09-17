//! Fixture dorada: mismos JSON que `tests/protocol/test_fixtures.py` del
//! lado Python, leídos por path relativo desde `../tests/protocol_fixtures/`
//! (fuente única).

use std::fs;
use std::path::PathBuf;

use rinthel::protocol::{
    CommandResult, ConfigPayload, ConfigSaveResult, CpuRamSample, DockerStatus, Envelope, GpuSample, LlamaStatus,
    LogLine, Theme,
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
fn llama_status_shape() {
    let env: Envelope = serde_json::from_str(&fixture("llama_status.json")).unwrap();
    assert_eq!(env.kind, "llama_status");
    let _: LlamaStatus = serde_json::from_value(env.data).expect("llama_status.json no matchea LlamaStatus");
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
fn capture_result_shape() {
    let result: CommandResult =
        serde_json::from_str(&fixture("capture_result.json")).expect("capture_result.json no matchea CommandResult");
    assert!(!result.results.is_empty());
}

#[test]
fn config_payload_shape() {
    let payload: ConfigPayload = serde_json::from_str(&fixture("config_payload.json"))
        .expect("config_payload.json no matchea ConfigPayload");
    assert!(!payload.services.is_empty());
    // moe: sin enabled/enabled_env (no es un LocalProcessService/DockerComposeService).
    let moe = payload.services.iter().find(|s| s.attr == "moe").expect("fixture sin moe");
    assert!(moe.enabled.is_none());
    assert!(moe.enabled_env.is_none());
    // llama: campos de al menos 2 grupos distintos (ver screens::settings::detail_rows).
    let llama = payload.services.iter().find(|s| s.attr == "llama").expect("fixture sin llama");
    let groups: std::collections::HashSet<_> = llama.fields.iter().map(|f| f.group.as_str()).collect();
    assert!(groups.len() > 1);
}

#[test]
fn config_save_result_shape() {
    let result: ConfigSaveResult = serde_json::from_str(&fixture("config_save_result.json"))
        .expect("config_save_result.json no matchea ConfigSaveResult");
    assert!(!result.ok);
    assert!(!result.errors.is_empty());
}
