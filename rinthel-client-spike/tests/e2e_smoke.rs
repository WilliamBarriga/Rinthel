//! Esqueleto de smoke E2E (sesión 00 del porteo): daemon real
//! (`rinthel_tui.daemon`, lanzado como subproceso) + cliente real (los
//! mismos structs `protocol.rs` + `reqwest`/`tokio-tungstenite` que usa
//! `app.rs`) conectados por HTTP/WS real en loopback — boot→terminate→cerrar.
//!
//! Desde sesión 04 (hardening), `boot`/`terminate` corren `run_phase_list`
//! REAL — pero contra dobles de `LocalProcessService`/`DockerComposeService`,
//! nunca contra llama-server/Understory/Pithagoras reales (ver
//! `../../tests/fixtures/fake_ready_server.py`): las env vars de abajo
//! redirigen los 3 managed services a un único proceso Python que solo
//! responde 200 en los puertos de prueba, y a directorios docker inexistentes
//! (`phase_up`/`phase_down` los saltean con un warn, sin invocar `docker
//! compose`). Único componente real e inevitable: el chequeo de
//! `systemctl is-active docker` al principio de boot — lee el estado real
//! del docker daemon del host, no lo simula (no hay hook para eso hoy); en
//! este proyecto (sin CI, corrido a mano) siempre corre con Docker ya activo.
//!
//! Lo que valida es el cable completo: WS/HTTP, serialización, el wiring
//! real de `lifecycle/runner.py` de punta a punta, cliente parseando en vivo
//! (ver .scratch/ratatui-migration/issues/08-cross-process-testing-strategy.md).
//!
//! Requiere que no haya nada más escuchando ya en :8765 ni en los puertos de
//! prueba 18080-18082 (proyecto de un solo dev/host, sin CI — cortá
//! cualquier `rinthel_tui.daemon` que tengas corriendo antes de `cargo test`).

use std::process::{Child, Command, Stdio};
use std::time::Duration;

use futures_util::StreamExt;
use rinthel_client_spike::protocol::{CommandResult, Envelope, Theme};
use tokio::sync::mpsc;

const DAEMON: &str = "http://127.0.0.1:8765";
const WS: &str = "ws://127.0.0.1:8765/ws/monitor";

// Puertos de prueba para los dobles de llama-server/Understory/Pithagoras —
// distintos de los defaults reales (8080/3800/4100) y del puerto del propio
// daemon (8765), para no chocar con nada que ya esté corriendo de verdad.
const FAKE_LLAMA_PORT: u16 = 18080;
const FAKE_UNDERSTORY_PORT: u16 = 18081;
const FAKE_PITHAGORAS_PORT: u16 = 18082;

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
    let fake_bin = format!("{repo_root}/tests/fixtures/fake_ready_server.py");
    let tmp = std::env::temp_dir();
    let scratch = tmp.join(format!("rinthel-e2e-smoke-{}", std::process::id()));
    let child = Command::new(&python)
        .args(["-m", "rinthel_tui.daemon"])
        .current_dir(repo_root)
        .env("RINTHEL_LLAMA_BIN", &fake_bin)
        .env("RINTHEL_LLAMA_PORT", FAKE_LLAMA_PORT.to_string())
        .env("RINTHEL_LLAMA_LOG_PATH", scratch.join("llama.log"))
        .env("RINTHEL_UNDERSTORY_DIR", scratch.join("understory-no-existe"))
        .env("RINTHEL_UNDERSTORY_PORT", FAKE_UNDERSTORY_PORT.to_string())
        .env("RINTHEL_PITHAGORAS_DIR", scratch.join("pithagoras-no-existe"))
        .env("RINTHEL_PITHAGORAS_PORT", FAKE_PITHAGORAS_PORT.to_string())
        .env(
            "RINTHEL_E2E_FAKE_PORTS",
            format!("{FAKE_LLAMA_PORT},{FAKE_UNDERSTORY_PORT},{FAKE_PITHAGORAS_PORT}"),
        )
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap_or_else(|e| panic!("no pude lanzar {python} -m rinthel_tui.daemon: {e}"));
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
    panic!("rinthel_tui.daemon no respondió GET /theme a tiempo (¿está libre el puerto 8765?)");
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
        matches!(
            env.kind.as_str(),
            "docker_status" | "gpu_sample" | "cpu_ram_sample" | "log_line" | "llama_status"
        ),
        "tipo de mensaje inesperado: {}",
        env.kind
    );

    // Amendment de docs/adr/0001 (sesión 05): boot/terminate real también
    // debe transmitir phase_status/phase_log por el mismo túnel mientras
    // corre — se recolectan en paralelo a los POST de abajo.
    let (kind_tx, mut kind_rx) = mpsc::unbounded_channel::<String>();
    tokio::spawn(async move {
        while let Some(Ok(msg)) = read.next().await {
            if let Ok(text) = msg.into_text() {
                if let Ok(env) = serde_json::from_str::<Envelope>(&text) {
                    let _ = kind_tx.send(env.kind);
                }
            }
        }
    });

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
    assert!(boot.results.iter().all(|r| r.ok), "boot real (contra dobles) no debería fallar");

    let terminate: CommandResult = client
        .post(format!("{DAEMON}/terminate"))
        .send()
        .await
        .expect("POST /terminate falló")
        .json()
        .await
        .expect("respuesta de /terminate no matchea CommandResult");
    assert!(terminate.results.iter().all(|r| r.ok), "terminate real (contra dobles) no debería fallar");

    // Deja que el reader procese los últimos frames en vuelo antes de leer.
    tokio::time::sleep(Duration::from_millis(200)).await;
    let mut kinds = Vec::new();
    while let Ok(kind) = kind_rx.try_recv() {
        kinds.push(kind);
    }
    assert!(
        kinds.iter().any(|k| k == "phase_status"),
        "no llegó ningún phase_status durante boot+terminate; vistos: {kinds:?}"
    );
    assert!(
        kinds.iter().any(|k| k == "phase_log"),
        "no llegó ningún phase_log durante boot+terminate; vistos: {kinds:?}"
    );
    // Sesión 08: llama_status es un estado parado (loop cada 2s mientras haya
    // cliente conectado, no un evento de la corrida) — boot+terminate contra
    // los dobles tarda bastante más que eso, así que debería aparecer solo.
    assert!(
        kinds.iter().any(|k| k == "llama_status"),
        "no llegó ningún llama_status durante boot+terminate; vistos: {kinds:?}"
    );
}

/// Sesión 06: `/reload` corre shutdown→boot→rebuild en secuencia contra los
/// mismos dobles — arranca desde cero (nada corriendo todavía), así que el
/// shutdown inicial mata/baja procesos que nunca existieron (warns, no
/// errores) antes de relanzar. Sin este boot previo la aserción seguiría
/// pasando igual (phase_kill/phase_down toleran "no había nada corriendo"),
/// pero arrancar ya booteado es el caso real (RELOAD desde el menú, con
/// todo arriba).
#[tokio::test]
async fn reload_over_real_wire() {
    let _daemon = spawn_daemon();
    let _theme = wait_for_theme().await;

    // Amendment de docs/adr/0001 (sesión 10): /reload real también debe
    // transmitir phase_batch("boot")/phase_batch("rebuild") por el mismo
    // túnel — sin esto el cliente no tiene forma de disparar Datamosh/
    // Vignette en el límite entre tandas.
    let (ws_stream, _) = tokio_tungstenite::connect_async(WS).await.expect("no pude conectar a /ws/monitor");
    let (_write, mut read) = ws_stream.split();
    let (batch_tx, mut batch_rx) = mpsc::unbounded_channel::<String>();
    tokio::spawn(async move {
        while let Some(Ok(msg)) = read.next().await {
            if let Ok(text) = msg.into_text() {
                if let Ok(env) = serde_json::from_str::<Envelope>(&text) {
                    if env.kind == "phase_batch" {
                        if let Ok(batch) = serde_json::from_value::<serde_json::Value>(env.data) {
                            if let Some(b) = batch.get("batch").and_then(|v| v.as_str()) {
                                let _ = batch_tx.send(b.to_string());
                            }
                        }
                    }
                }
            }
        }
    });

    let client = reqwest::Client::new();
    let boot: CommandResult = client
        .post(format!("{DAEMON}/boot"))
        .send()
        .await
        .expect("POST /boot falló")
        .json()
        .await
        .expect("respuesta de /boot no matchea CommandResult");
    assert!(boot.results.iter().all(|r| r.ok), "boot previo (contra dobles) no debería fallar");

    let reload: CommandResult = client
        .post(format!("{DAEMON}/reload"))
        .send()
        .await
        .expect("POST /reload falló")
        .json()
        .await
        .expect("respuesta de /reload no matchea CommandResult");
    assert!(
        reload.results.iter().all(|r| r.ok),
        "reload real (contra dobles) no debería fallar: {:?}",
        reload.results
    );
    // shutdown (kill llama + down x2 + wait-port-free = 4 unidades) + DOCKER
    // (1) + boot (spawn+wait llama, 1 unidad) + rebuild (up+wait x2) — mismo
    // total que specs.reload_units + el chequeo de DOCKER que daemon.py
    // inserta aparte.
    assert_eq!(reload.results.len(), 8, "resultados: {:?}", reload.results);

    tokio::time::sleep(Duration::from_millis(200)).await;
    let mut batches = Vec::new();
    while let Ok(b) = batch_rx.try_recv() {
        batches.push(b);
    }
    assert_eq!(batches, vec!["boot", "rebuild"], "phase_batch visto durante /reload real: {batches:?}");
}
