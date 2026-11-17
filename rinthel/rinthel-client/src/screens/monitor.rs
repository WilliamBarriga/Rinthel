//! Screen de monitor: los servicios y los Local models tal como los reporta
//! `models_status`, la telemetría del host, los contenedores y el log.

use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Row, Sparkline, Table};
use ratatui::Frame;
use ratatui_sci_fi::{EnergyGauge, Theme as SciFiTheme};

use crate::app::{App, Colors};
use crate::protocol::{CapabilityStatus, ServiceState, ServiceStatus};
use crate::widgets::log_tail;

fn online_badge(online: bool, colors: &Colors) -> Span<'static> {
    if online {
        Span::styled(" ONLINE ", Style::default().fg(colors.bg).bg(colors.success))
    } else {
        Span::styled(" OFFLINE ", Style::default().fg(colors.bg).bg(colors.hot))
    }
}

/// Una línea de `models_status`: `<Capability> · <Local model o —> ·
/// <estado>`, más el error si el activo no puede correr.
fn capability_row(line: &CapabilityStatus, colors: &Colors) -> Line<'static> {
    let (state, color) = match line.state {
        ServiceState::Ready => ("listo", colors.success),
        ServiceState::Down => ("no responde", colors.hot),
        ServiceState::Off => ("apagado", colors.dim),
    };
    let mut spans = vec![
        Span::raw(format!(" {} · {} · ", line.capability, line.model.as_deref().unwrap_or("—"))),
        Span::styled(state, Style::default().fg(color)),
    ];
    if let Some(error) = &line.error {
        spans.push(Span::styled(format!(" — {error}"), Style::default().fg(colors.hot)));
    }
    Line::from(spans)
}

/// Una fila por managed service que el daemon reporta, ordenadas por nombre:
/// el cliente no suma ni saca servicios.
fn service_badges(services: &[ServiceStatus], colors: &Colors) -> Line<'static> {
    let mut sorted: Vec<&ServiceStatus> = services.iter().collect();
    sorted.sort_by(|a, b| a.name.cmp(&b.name));
    let spans = sorted
        .into_iter()
        .flat_map(|s| [Span::raw(format!("   {}", s.name)), online_badge(s.state == ServiceState::Ready, colors)])
        .collect::<Vec<_>>();
    Line::from(spans)
}

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // service badges
            Constraint::Length(app.models_status.capabilities.len() as u16 + 2), // models_status
            Constraint::Length(3),  // ratatui-sci-fi EnergyGauge experiment
            Constraint::Length(9),  // sparklines
            Constraint::Min(6),     // docker table + log
            Constraint::Length(3),  // footer/status
        ])
        .split(area);

    let badges = Paragraph::new(service_badges(&app.models_status.services, &app.colors))
        .block(Block::default().borders(Borders::ALL).title(" services "));
    f.render_widget(badges, rows[0]);

    let models: Vec<Line> = app.models_status.capabilities.iter().map(|l| capability_row(l, &app.colors)).collect();
    f.render_widget(
        Paragraph::new(models).block(Block::default().borders(Borders::ALL).title(" local models ")),
        rows[1],
    );

    // ratatui-sci-fi EnergyGauge: trae su propia cascada CSS interna, solo
    // hace falta elegir el Theme, no hay que tocar ratatui_style a mano.
    // Comparar contra los Sparkline de abajo, que son ratatui puro con los
    // colores servidos por /theme.
    let gauge_cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Ratio(1, 3); 3])
        .split(rows[2]);
    f.render_widget(
        EnergyGauge::new(app.cpu_ram.cpu_percent / 100.0).label("CPU").theme(SciFiTheme::Cyberpunk),
        gauge_cols[0],
    );
    f.render_widget(
        EnergyGauge::new(app.cpu_ram.ram_percent / 100.0).label("RAM").theme(SciFiTheme::Cyberpunk),
        gauge_cols[1],
    );
    f.render_widget(
        EnergyGauge::new(app.gpu.utilization.unwrap_or(0.0) / 100.0).label("GPU").theme(SciFiTheme::Cyberpunk),
        gauge_cols[2],
    );

    let spark_cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Ratio(1, 3); 3])
        .split(rows[3]);

    let cpu_data: Vec<u64> = app.cpu_hist.iter().copied().collect();
    f.render_widget(
        Sparkline::default()
            .block(Block::default().borders(Borders::ALL).title(format!(
                " CPU {:.0}% ",
                app.cpu_ram.cpu_percent
            )))
            .data(&cpu_data)
            .style(Style::default().fg(app.colors.success)),
        spark_cols[0],
    );
    let ram_data: Vec<u64> = app.ram_hist.iter().copied().collect();
    f.render_widget(
        Sparkline::default()
            .block(Block::default().borders(Borders::ALL).title(format!(
                " RAM {:.0}% ({:.1}/{:.1}GB) ",
                app.cpu_ram.ram_percent, app.cpu_ram.ram_used_gb, app.cpu_ram.ram_total_gb
            )))
            .data(&ram_data)
            .style(Style::default().fg(app.colors.accent)),
        spark_cols[1],
    );
    let gpu_title = if app.gpu.available {
        format!(
            " GPU {:.0}% {:.0}°C  {:.0}/{:.0}MiB ",
            app.gpu.utilization.unwrap_or(0.0),
            app.gpu.temperature.unwrap_or(0.0),
            app.gpu.memory_used.unwrap_or(0.0),
            app.gpu.memory_total.unwrap_or(0.0),
        )
    } else {
        " GPU N/A ".to_string()
    };
    let gpu_data: Vec<u64> = app.gpu_hist.iter().copied().collect();
    f.render_widget(
        Sparkline::default()
            .block(Block::default().borders(Borders::ALL).title(gpu_title))
            .data(&gpu_data)
            .style(Style::default().fg(app.colors.warn)),
        spark_cols[2],
    );

    let mid_cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(rows[4]);

    let table_rows: Vec<Row> = app
        .containers
        .iter()
        .map(|c| Row::new(vec![c.name.clone(), c.state.clone(), c.status.clone()]))
        .collect();
    let table = Table::new(
        table_rows,
        [Constraint::Percentage(40), Constraint::Percentage(20), Constraint::Percentage(40)],
    )
    .header(Row::new(vec!["name", "state", "status"]).style(Style::default().fg(app.colors.dim)))
    .block(Block::default().borders(Borders::ALL).title(" docker "));
    f.render_widget(table, mid_cols[0]);

    log_tail::draw(
        f,
        mid_cols[1],
        &app.log_lines,
        app.colors.fg,
        " log_tail (llama-server) — ←→ ",
        app.log_scroll_x,
    );

    f.render_widget(Paragraph::new(super::status_line(app)).block(Block::default().borders(Borders::ALL)), rows[5]);
}
