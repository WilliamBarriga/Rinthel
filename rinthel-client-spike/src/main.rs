//! SPIKE — cliente Ratatui, no producción. Ver rinthel_tui/daemon.py
//! y .scratch/ratatui-migration/issues/05-mvp-spike.md para el contrato.
//!
//! Corré (con el daemon ya arriba en :8765):
//!   cargo run

use std::io;

use rinthel_client_spike::app::{App, DAEMON};
use rinthel_client_spike::protocol::Theme;

#[tokio::main]
async fn main() -> io::Result<()> {
    let theme: Theme = reqwest::get(format!("{DAEMON}/theme"))
        .await
        .expect("GET /theme — ¿está corriendo el daemon? (.venv/bin/python -m rinthel_tui.daemon)")
        .json()
        .await
        .expect("theme JSON inválido");

    App::new(&theme).run().await
}
