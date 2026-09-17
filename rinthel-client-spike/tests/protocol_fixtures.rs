//! Fixture dorada (sesión 00 del porteo): mismos JSON que
//! `tests/protocol/test_fixtures.py` del lado Python, leídos por path
//! relativo desde `../tests/protocol_fixtures/` (fuente única, ver
//! .scratch/ratatui-migration/issues/08-cross-process-testing-strategy.md).

use std::fs;
use std::path::PathBuf;

use rinthel_client_spike::protocol::{CommandResult, CpuRamSample, DockerStatus, Envelope, GpuSample, LogLine, Theme};

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
