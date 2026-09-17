//! Esqueleto de smoke E2E (sesión 00 del porteo): daemon real
//! (`daemon_spike.py`, lanzado como subproceso) + cliente real (los mismos
//! structs `protocol.rs` + `reqwest`/`tokio-tungstenite` que usa `app.rs`)
//! conectados por HTTP/WS real en loopback — boot→terminate→cerrar.
//!
//! `boot`/`terminate` son los simulados de hoy (nunca tocan llama-server ni
//! docker real — ver docstring de `daemon_spike.py`), así que esto no
//! depende de que sean reales todavía (eso es la sesión 04 de hardening).
//! Lo que valida es el cable: WS/HTTP, serialización, cliente parseando en
//! vivo (ver .scratch/ratatui-migration/issues/08-cross-process-testing-strategy.md).
//!
//! Requiere que no haya nada más escuchando ya en :8765 (proyecto de un
//! solo dev/host, sin CI — cortá cualquier `daemon_spike.py` que tengas
//! corriendo antes de `cargo test`).

use std::process::{Child, Command, Stdio};
use std::time::Duration;

use futures_util::StreamExt;
use rinthel_client_spike::protocol::{CommandResult, Envelope, Theme};

const DAEMON: &str = "http://127.0.0.1:8765";
const WS: &str = "ws://127.0.0.1:8765/ws/monitor";

struct DaemonGuard(Child);

impl Drop for DaemonGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn spawn_daemon() -> DaemonGuard {
    let repo_root = concat!(env!("CARGO_MANIFEST_DIR"), "/..");
    let python = format!("{repo_root}/.venv/bin/python");
    let child = Command::new(&python)
        .args(["-m", "rinthel_tui.daemon_spike"])
        .current_dir(repo_root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap_or_else(|e| panic!("no pude lanzar {python} -m rinthel_tui.daemon_spike: {e}"));
    DaemonGuard(child)
}

async fn wait_for_theme() -> Theme {
    for _ in 0..50 {
        if let Ok(resp) = reqwest::get(format!("{DAEMON}/theme")).await {
            if let Ok(theme) = resp.json::<Theme>().await {
                return theme;
            }
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    panic!("daemon_spike.py no respondió GET /theme a tiempo (¿está libre el puerto 8765?)");
}

#[tokio::test]
async fn boot_then_terminate_over_real_wire() {
    let _daemon = spawn_daemon();
    let _theme = wait_for_theme().await;

    // Cable de streaming: conectar y parsear al menos un mensaje real con
    // los mismos structs que usa el cliente de producción.
    let (ws_stream, _) = tokio_tungstenite::connect_async(WS)
        .await
        .expect("no pude conectar a /ws/monitor");
    let (_write, mut read) = ws_stream.split();
    let first = read
        .next()
        .await
        .expect("el stream se cerró sin mandar nada")
        .expect("frame WS inválido");
    let text = first.into_text().expect("frame no-texto");
    let env: Envelope = serde_json::from_str(&text).expect("sobre {type,data} inválido");
    assert!(
        matches!(env.kind.as_str(), "docker_status" | "gpu_sample" | "cpu_ram_sample" | "log_line"),
        "tipo de mensaje inesperado: {}",
        env.kind
    );

    // Comandos bloqueantes reales, en el orden boot→terminate→cerrar.
    let client = reqwest::Client::new();
    let boot: CommandResult = client
        .post(format!("{DAEMON}/boot"))
        .send()
        .await
        .expect("POST /boot falló")
        .json()
        .await
        .expect("respuesta de /boot no matchea CommandResult");
    assert!(boot.results.iter().all(|r| r.ok), "boot simulado no debería fallar");

    let terminate: CommandResult = client
        .post(format!("{DAEMON}/terminate"))
        .send()
        .await
        .expect("POST /terminate falló")
        .json()
        .await
        .expect("respuesta de /terminate no matchea CommandResult");
    assert!(terminate.results.iter().all(|r| r.ok), "terminate simulado no debería fallar");
}
