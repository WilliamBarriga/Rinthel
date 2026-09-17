//! Screen de monitor — `draw_monitor` movido tal cual desde `main.rs`
//! (sesión 00), con el helper `badge` que solo usa esta screen.

use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Row, Sparkline, Table};
use ratatui::Frame;
use ratatui_sci_fi::{EnergyGauge, Theme as SciFiTheme};

use crate::app::{App, Colors};
use crate::protocol::DockerContainer;

fn badge(containers: &[DockerContainer], name_contains: &str, colors: &Colors) -> Span<'static> {
    let running = containers
        .iter()
        .any(|c| c.name.contains(name_contains) && c.state == "running");
    if running {
        Span::styled(" ONLINE ", Style::default().fg(colors.bg).bg(colors.success))
    } else {
        Span::styled(" OFFLINE ", Style::default().fg(colors.bg).bg(colors.hot))
    }
}

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // service badges
            Constraint::Length(3),  // ratatui-sci-fi EnergyGauge experiment
            Constraint::Length(9),  // sparklines
            Constraint::Min(6),     // docker table + log
            Constraint::Length(3),  // footer/status
        ])
        .split(area);

    let badges = Paragraph::new(Line::from(vec![
        Span::raw(" llama-server "),
        Span::styled(" N/A (spike) ", Style::default().fg(app.colors.dim)),
        Span::raw("   understory "),
        badge(&app.containers, "understory", &app.colors),
        Span::raw("   pithagoras "),
        badge(&app.containers, "pithagoras", &app.colors),
    ]))
    .block(Block::default().borders(Borders::ALL).title(" services "));
    f.render_widget(badges, rows[0]);

    // Experimento ratatui-sci-fi (ticket 01/05): EnergyGauge trae su propia
    // cascada CSS interna — solo hace falta elegir el Theme, no hay que
    // tocar ratatui_style a mano. Comparar contra los Sparkline de abajo,
    // que son ratatui puro con los colores servidos por /theme.
    let gauge_cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Ratio(1, 3); 3])
        .split(rows[1]);
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
        .split(rows[2]);

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
        .split(rows[3]);

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

    let log_text: Vec<Line> = app
        .log_lines
        .iter()
        .rev()
        .take((mid_cols[1].height as usize).saturating_sub(2))
        .rev()
        .map(|l| Line::from(Span::styled(l.clone(), Style::default().fg(app.colors.fg))))
        .collect();
    let log = Paragraph::new(log_text).block(Block::default().borders(Borders::ALL).title(" log_tail (llama-server) "));
    f.render_widget(log, mid_cols[1]);

    f.render_widget(Paragraph::new(super::status_line(app)).block(Block::default().borders(Borders::ALL)), rows[4]);
}
