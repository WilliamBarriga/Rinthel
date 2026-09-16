//! SPIKE — cliente Ratatui, no producción. Ver rinthel_tui/daemon_spike.py
//! y .scratch/ratatui-migration/issues/05-mvp-spike.md para el contrato.
//!
//! Corré (con el daemon spike ya arriba en :8765):
//!   cargo run

mod protocol;

use std::collections::VecDeque;
use std::io;
use std::time::Duration;

use crossterm::event::{self, Event, KeyCode};
use crossterm::execute;
use crossterm::terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen};
use futures_util::StreamExt;
use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph, Row, Sparkline, Table};
use ratatui::{Frame, Terminal};
use ratatui::backend::CrosstermBackend;
use tokio::sync::mpsc;

use protocol::{CommandResult, DockerContainer, Envelope, GpuSample, CpuRamSample, Theme};
use ratatui_sci_fi::{EnergyGauge, Theme as SciFiTheme};

const DAEMON: &str = "http://127.0.0.1:8765";
const WS: &str = "ws://127.0.0.1:8765/ws/monitor";

/// Eventos que las tareas de fondo empujan hacia el loop principal —
/// mismo patrón que un `Message` en Elm/TEA, adaptado a Rust con un canal.
enum AppEvent {
    Docker(Vec<DockerContainer>),
    Gpu(GpuSample),
    CpuRam(CpuRamSample),
    Log(String),
    CommandDone(&'static str, CommandResult),
    CommandFailed(&'static str, String),
}

#[derive(PartialEq)]
enum Screen {
    Menu,
    Monitor,
}

struct Colors {
    fg: Color,
    accent: Color,
    warn: Color,
    success: Color,
    hot: Color,
    dim: Color,
    bg: Color,
}

fn hex(s: &str) -> Color {
    let s = s.trim_start_matches('#');
    let r = u8::from_str_radix(&s[0..2], 16).unwrap_or(255);
    let g = u8::from_str_radix(&s[2..4], 16).unwrap_or(255);
    let b = u8::from_str_radix(&s[4..6], 16).unwrap_or(255);
    Color::Rgb(r, g, b)
}

impl From<&Theme> for Colors {
    fn from(t: &Theme) -> Self {
        Colors {
            fg: hex(&t.canonical.fg),
            accent: hex(&t.canonical.accent),
            warn: hex(&t.canonical.warn),
            success: hex(&t.canonical.success),
            hot: hex(&t.canonical.hot),
            dim: hex(&t.canonical.dim),
            bg: hex(&t.canonical.bg),
        }
    }
}

struct App {
    screen: Screen,
    menu_selected: usize,
    colors: Colors,
    containers: Vec<DockerContainer>,
    gpu: GpuSample,
    cpu_ram: CpuRamSample,
    cpu_hist: VecDeque<u64>,
    ram_hist: VecDeque<u64>,
    gpu_hist: VecDeque<u64>,
    log_lines: VecDeque<String>,
    command_in_flight: Option<&'static str>,
    last_command_result: Option<(&'static str, CommandResult)>,
    last_command_error: Option<String>,
    should_quit: bool,
}

const MENU_ITEMS: [&str; 4] = ["MONITOR", "BOOT", "TERMINATE", "SALIR"];
const HIST_LEN: usize = 60;

impl App {
    fn new(theme: &Theme) -> Self {
        App {
            screen: Screen::Menu,
            menu_selected: 0,
            colors: Colors::from(theme),
            containers: Vec::new(),
            gpu: GpuSample::default(),
            cpu_ram: CpuRamSample::default(),
            cpu_hist: VecDeque::with_capacity(HIST_LEN),
            ram_hist: VecDeque::with_capacity(HIST_LEN),
            gpu_hist: VecDeque::with_capacity(HIST_LEN),
            log_lines: VecDeque::with_capacity(200),
            command_in_flight: None,
            last_command_result: None,
            last_command_error: None,
            should_quit: false,
        }
    }

    fn push_hist(hist: &mut VecDeque<u64>, v: u64) {
        if hist.len() == HIST_LEN {
            hist.pop_front();
        }
        hist.push_back(v);
    }

    fn apply(&mut self, ev: AppEvent) {
        match ev {
            AppEvent::Docker(c) => self.containers = c,
            AppEvent::Gpu(g) => {
                if let Some(u) = g.utilization {
                    Self::push_hist(&mut self.gpu_hist, u.round() as u64);
                }
                self.gpu = g;
            }
            AppEvent::CpuRam(c) => {
                Self::push_hist(&mut self.cpu_hist, c.cpu_percent.round() as u64);
                Self::push_hist(&mut self.ram_hist, c.ram_percent.round() as u64);
                self.cpu_ram = c;
            }
            AppEvent::Log(line) => {
                if self.log_lines.len() == 200 {
                    self.log_lines.pop_front();
                }
                self.log_lines.push_back(line);
            }
            AppEvent::CommandDone(name, result) => {
                self.command_in_flight = None;
                self.last_command_error = None;
                self.last_command_result = Some((name, result));
            }
            AppEvent::CommandFailed(name, err) => {
                self.command_in_flight = None;
                self.last_command_error = Some(format!("{name} falló: {err}"));
            }
        }
    }
}

async fn ws_task(tx: mpsc::UnboundedSender<AppEvent>) {
    loop {
        let conn = tokio_tungstenite::connect_async(WS).await;
        let Ok((stream, _)) = conn else {
            tokio::time::sleep(Duration::from_secs(2)).await;
            continue;
        };
        let (_write, mut read) = stream.split();
        while let Some(Ok(msg)) = read.next().await {
            let tokio_tungstenite::tungstenite::Message::Text(text) = msg else { continue };
            let Ok(env) = serde_json::from_str::<Envelope>(&text) else { continue };
            let ev = match env.kind.as_str() {
                "docker_status" => serde_json::from_value::<protocol::DockerStatus>(env.data)
                    .ok()
                    .map(|d| AppEvent::Docker(d.containers)),
                "gpu_sample" => serde_json::from_value::<GpuSample>(env.data).ok().map(AppEvent::Gpu),
                "cpu_ram_sample" => serde_json::from_value::<CpuRamSample>(env.data).ok().map(AppEvent::CpuRam),
                "log_line" => serde_json::from_value::<protocol::LogLine>(env.data)
                    .ok()
                    .map(|l| AppEvent::Log(l.line)),
                _ => None,
            };
            if let Some(ev) = ev {
                if tx.send(ev).is_err() {
                    return;
                }
            }
        }
        // reconexión sin replay (ADR 0001): volvemos al top del loop y
        // el próximo connect trae estado fresco.
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}

async fn run_command(name: &'static str, path: &str, tx: mpsc::UnboundedSender<AppEvent>) {
    let url = format!("{DAEMON}{path}");
    match reqwest::Client::new().post(&url).send().await {
        Ok(resp) => match resp.json::<CommandResult>().await {
            Ok(result) => {
                let _ = tx.send(AppEvent::CommandDone(name, result));
            }
            Err(e) => {
                let _ = tx.send(AppEvent::CommandFailed(name, e.to_string()));
            }
        },
        Err(e) => {
            let _ = tx.send(AppEvent::CommandFailed(name, e.to_string()));
        }
    }
}

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

fn draw_menu(f: &mut Frame, app: &App) {
    let area = f.area();
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(5), Constraint::Min(0), Constraint::Length(3)])
        .split(area);

    let title = Paragraph::new(vec![
        Line::from(Span::styled(
            "R I N T H E L",
            Style::default().fg(app.colors.accent).add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(
            "ratatui spike — ticket 05",
            Style::default().fg(app.colors.dim),
        )),
    ])
    .block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(app.colors.accent)));
    f.render_widget(title, chunks[0]);

    let items: Vec<ListItem> = MENU_ITEMS
        .iter()
        .enumerate()
        .map(|(i, label)| {
            let style = if i == app.menu_selected {
                Style::default().fg(app.colors.bg).bg(app.colors.accent).add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(app.colors.fg)
            };
            ListItem::new(format!("  {label}")).style(style)
        })
        .collect();
    let list = List::new(items).block(
        Block::default()
            .borders(Borders::ALL)
            .title(" jack in ")
            .border_style(Style::default().fg(app.colors.dim)),
    );
    f.render_widget(list, chunks[1]);

    f.render_widget(
        Paragraph::new(status_line(app)).block(Block::default().borders(Borders::ALL)),
        chunks[2],
    );
}

fn draw_monitor(f: &mut Frame, app: &App) {
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
        format!(" GPU {:.0}% {:.0}°C ", app.gpu.utilization.unwrap_or(0.0), app.gpu.temperature.unwrap_or(0.0))
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

    f.render_widget(Paragraph::new(status_line(app)).block(Block::default().borders(Borders::ALL)), rows[4]);
}

/// Feedback de boot/terminate — antes solo la pintaba `draw_monitor`, así
/// que dispararlos desde el menú (Enter sobre BOOT/TERMINATE) no mostraba
/// nada hasta cambiar de pantalla. Factoreado para que ambas screens lo usen.
fn status_line(app: &App) -> Line<'static> {
    if let Some(name) = app.command_in_flight {
        Line::from(Span::styled(
            format!(" {name}... (bloqueante, protocolo POST) "),
            Style::default().fg(app.colors.warn),
        ))
    } else if let Some(err) = &app.last_command_error {
        Line::from(Span::styled(format!(" {err} "), Style::default().fg(app.colors.hot)))
    } else if let Some((name, result)) = &app.last_command_result {
        let ok_count = result.results.iter().filter(|r| r.ok).count();
        Line::from(Span::styled(
            format!(" {name}: {ok_count}/{} ok ", result.results.len()),
            Style::default().fg(app.colors.success),
        ))
    } else {
        let hint = match app.screen {
            Screen::Menu => " ↑↓=mover  Enter=elegir  q=salir ",
            Screen::Monitor => " b=boot  t=terminate  Esc=menu  q=salir ",
        };
        Line::from(Span::styled(hint, Style::default().fg(app.colors.dim)))
    }
}

fn draw(f: &mut Frame, app: &App) {
    let bg = Block::default().style(Style::default().bg(app.colors.bg));
    f.render_widget(bg, f.area());
    match app.screen {
        Screen::Menu => draw_menu(f, app),
        Screen::Monitor => draw_monitor(f, app),
    }
}

#[tokio::main]
async fn main() -> io::Result<()> {
    let theme: Theme = reqwest::get(format!("{DAEMON}/theme"))
        .await
        .expect("GET /theme — ¿está corriendo el daemon spike? (.venv/bin/python -m rinthel_tui.daemon_spike)")
        .json()
        .await
        .expect("theme JSON inválido");

    let mut app = App::new(&theme);

    let (tx, mut rx) = mpsc::unbounded_channel::<AppEvent>();
    tokio::spawn(ws_task(tx.clone()));

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let result = (async {
        loop {
            terminal.draw(|f| draw(f, &app))?;

            while let Ok(ev) = rx.try_recv() {
                app.apply(ev);
            }

            if event::poll(Duration::from_millis(80))? {
                if let Event::Key(key) = event::read()? {
                    match (&app.screen, key.code) {
                        (_, KeyCode::Char('q')) => app.should_quit = true,
                        (Screen::Menu, KeyCode::Up) => {
                            app.menu_selected = app.menu_selected.saturating_sub(1);
                        }
                        (Screen::Menu, KeyCode::Down) => {
                            app.menu_selected = (app.menu_selected + 1).min(MENU_ITEMS.len() - 1);
                        }
                        (Screen::Menu, KeyCode::Enter) => match app.menu_selected {
                            0 => app.screen = Screen::Monitor,
                            1 => {
                                app.command_in_flight = Some("boot");
                                tokio::spawn(run_command("boot", "/boot", tx.clone()));
                            }
                            2 => {
                                app.command_in_flight = Some("terminate");
                                tokio::spawn(run_command("terminate", "/terminate", tx.clone()));
                            }
                            3 => app.should_quit = true,
                            _ => {}
                        },
                        (Screen::Monitor, KeyCode::Esc) => app.screen = Screen::Menu,
                        (Screen::Monitor, KeyCode::Char('b')) => {
                            app.command_in_flight = Some("boot");
                            tokio::spawn(run_command("boot", "/boot", tx.clone()));
                        }
                        (Screen::Monitor, KeyCode::Char('t')) => {
                            app.command_in_flight = Some("terminate");
                            tokio::spawn(run_command("terminate", "/terminate", tx.clone()));
                        }
                        _ => {}
                    }
                }
            }

            if app.should_quit {
                break;
            }
        }
        Ok::<(), io::Error>(())
    })
    .await;

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    result
}
