//! Screen de menú — itera el registro `super::MENU_ENTRIES`.
//!
//! Título + tagline: reveal `GlitchLabel`/rotación `RotatingTagline`, con
//! estado en `App::menu_title`/`App::menu_tagline` (avanzado cada vuelta del
//! loop en `App::run`) — acá solo se lee el texto que corresponde a este
//! instante.

use std::time::Instant;

use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph};
use ratatui::Frame;

use crate::app::App;

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(5), Constraint::Min(0), Constraint::Length(3)])
        .split(area);

    let now = Instant::now();
    let title = Paragraph::new(vec![
        Line::from(Span::styled(
            app.menu_title.text(now).to_string(),
            Style::default().fg(app.colors.accent).add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(app.menu_tagline.text(now).to_string(), Style::default().fg(app.colors.dim))),
    ])
    .block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(app.colors.accent)));
    f.render_widget(title, chunks[0]);

    let items: Vec<ListItem> = super::MENU_ENTRIES
        .iter()
        .enumerate()
        .map(|(i, item)| match item {
            super::MenuItem::Entry(entry) => {
                let style = if i == app.menu_selected {
                    Style::default().fg(app.colors.bg).bg(app.colors.accent).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(app.colors.fg)
                };
                ListItem::new(format!("  {}", entry.label)).style(style)
            }
            // Nunca seleccionable — Up/Down (next_selectable/prev_selectable
            // en screens/mod.rs) lo saltan, así que no necesita reaccionar a
            // `app.menu_selected`.
            super::MenuItem::Divider => {
                ListItem::new("  ───────────────").style(Style::default().fg(app.colors.dim))
            }
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
        Paragraph::new(super::status_line(app)).block(Block::default().borders(Borders::ALL)),
        chunks[2],
    );
}
