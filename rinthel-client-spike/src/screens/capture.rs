//! Screen de captura de perfil MoE — puerto de
//! `rinthel_tui/tui/screens/capture.py` (sesión 03 del port-map). A
//! diferencia de boot/terminate (que solo pintan `status_line` en el pie de
//! Menu/Monitor), esta sesión sí trae una screen dedicada — así lo pide el
//! ticket 03, y refleja que `CaptureScreen` en Python bloquea la vuelta al
//! menú hasta terminar (`action_dismiss_if_done`).
//!
//! Decisión de protocolo (grillada con Tarkark 2026-09-16, la pregunta que
//! el propio ticket 03 exigía resolver antes de portar): `POST /capture`
//! bloqueante, mismo shape `CommandResult`/`ServiceOutcome` que
//! `/boot`/`/terminate` (Opción A), no un tag nuevo en `/ws/monitor`
//! (Opción B). Motivo: `managed_service._run` del lado Python ya reporta
//! stdout/stderr como un solo blob con `proc.communicate()` al terminar
//! cada sub-paso, no lo streamea línea por línea — el "feedback en vivo"
//! que ofrecía la Opción B en el ticket eran en realidad los 2 anuncios de
//! arranque ("Capturando perfil 'código'...", "...'chat'..."), no progreso
//! fino. Se pierden esos 2 anuncios; a cambio, cero desvío de ADR 0001 y
//! cero primer-uso-no-comando del túnel WS.
//!
//! `ServiceOutcome.service` se reusa para nombrar cada sub-paso ("código"/
//! "chat") en vez de un servicio real — mismo truco de "pedir prestado un
//! tipo" que el propio ticket ya aprobaba para `ScreenPhaseReport`.
//!
//! `daemon_spike.py::/capture` está simulado (delays fijos, sin tocar la
//! GPU), igual que `/boot`/`/terminate` — decisión de Tarkark 2026-09-16.
//! A diferencia de boot/terminate, no hay sesión de hardening "capture
//! real" en el port-map todavía; anotado en "Not yet specified".

use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;

use crate::app::App;

const TITLE: &str = " ◈ MOE PROFILE CAPTURE — Qwen3.6-35B-A3B ";

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(0)])
        .split(area);

    let (status, status_color, body) = if app.command_in_flight == Some("capture") {
        (
            "○ capturando perfil de expertos…".to_string(),
            app.colors.warn,
            vec![Line::from(Span::styled(
                "esperando resultado (POST /capture bloqueante, sin progreso intermedio)...",
                Style::default().fg(app.colors.dim),
            ))],
        )
    } else if let Some(("capture", result)) = &app.last_command_result {
        let ok_all = result.results.iter().all(|r| r.ok);
        let lines = result
            .results
            .iter()
            .map(|r| {
                let mark = if r.ok { "●" } else { "✖" };
                let color = if r.ok { app.colors.success } else { app.colors.hot };
                Line::from(Span::styled(format!("{mark} {}: {}", r.service, r.message), Style::default().fg(color)))
            })
            .collect();
        let status = if ok_all { "● perfil capturado".to_string() } else { "✖ falló la captura".to_string() };
        (status, if ok_all { app.colors.success } else { app.colors.hot }, lines)
    } else if let Some(err) = &app.last_command_error {
        (format!("✖ falló: {err}"), app.colors.hot, Vec::new())
    } else {
        ("○ capturando perfil de expertos…".to_string(), app.colors.warn, Vec::new())
    };

    let status_line = Paragraph::new(Line::from(Span::styled(status, Style::default().fg(status_color))));
    f.render_widget(status_line, rows[0]);

    let log = Paragraph::new(body).block(Block::default().borders(Borders::ALL).title(TITLE));
    f.render_widget(log, rows[1]);
}

/// `action_dismiss_if_done` de `capture.py`: acá no hay callback, así que
/// `app.rs` consulta esto para decidir si Esc vuelve al menú.
pub fn done(app: &App) -> bool {
    app.command_in_flight.is_none()
}
