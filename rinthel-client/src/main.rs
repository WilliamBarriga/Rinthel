//! Cliente Ratatui de Rinthel. Ver `rinthel_tui/daemon.py` y
//! .scratch/ratatui-migration/issues/05-mvp-spike.md para el contrato.
//!
//! Uso normal: `rinthel-boot.sh` (autostart del daemon + pidfile, sesión 11
//! del port-map) — corre este binario directo solo para debugging puntual.
//! Acepta `--port <N>` (default 8765) para apuntar a un daemon en otro
//! puerto; sin el flag asume que ya está arriba ahí
//! (`.venv/bin/python -m rinthel_tui.daemon`).

use std::io;

use rinthel::app::{self, App};
use rinthel::protocol::Theme;

#[tokio::main]
async fn main() -> io::Result<()> {
    if let Some(port) = parse_port_arg() {
        app::set_daemon_port(port);
    }
    let daemon = app::daemon_base();
    let theme: Theme = reqwest::get(format!("{daemon}/theme"))
        .await
        .expect("GET /theme — ¿está corriendo el daemon? (.venv/bin/python -m rinthel_tui.daemon)")
        .json()
        .await
        .expect("theme JSON inválido");

    App::new(&theme).run().await
}

/// Parseo manual de `--port <N>` — sin sumar `clap` por un solo flag
/// opcional, mismo criterio "sin meter una herramienta más" de ADR 0001.
fn parse_port_arg() -> Option<u16> {
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--port" {
            return args.next()?.parse().ok();
        }
    }
    None
}
