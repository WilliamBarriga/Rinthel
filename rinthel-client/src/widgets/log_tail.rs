//! Tail en vivo de log, como widget reusable — lo comparten
//! `screens::monitor` (panel mini) y `screens::logs` (pantalla completa),
//! sin duplicar el recorte de líneas visibles.

use std::collections::VecDeque;

use ratatui::layout::{Margin, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Scrollbar, ScrollbarOrientation, ScrollbarState};
use ratatui::Frame;

/// `scroll_x` es el offset horizontal en columnas (`App::log_scroll_x`,
/// movido con `Left`/`Right`) — las líneas de llama-server suelen superar
/// el ancho del panel, así que sin esto quedaban truncadas sin forma de
/// leerlas enteras. El slider de abajo (`Scrollbar` horizontal sobre el
/// borde inferior del bloque) es el único indicativo de que hay más texto
/// a la derecha, ya que `Paragraph` no lo señala por su cuenta.
pub fn draw(f: &mut Frame, area: Rect, lines: &VecDeque<String>, fg: Color, title: &str, scroll_x: u16) {
    let visible: Vec<Line> = lines
        .iter()
        .rev()
        .take((area.height as usize).saturating_sub(2))
        .rev()
        .map(|l| Line::from(Span::styled(l.clone(), Style::default().fg(fg))))
        .collect();
    let widget = Paragraph::new(visible)
        .scroll((0, scroll_x))
        .block(Block::default().borders(Borders::ALL).title(title));
    f.render_widget(widget, area);

    let max_len = lines.iter().map(|l| l.chars().count()).max().unwrap_or(0);
    let mut scroll_state = ScrollbarState::new(max_len).position(scroll_x as usize);
    let scrollbar = Scrollbar::new(ScrollbarOrientation::HorizontalBottom)
        .begin_symbol(Some("◄"))
        .end_symbol(Some("►"))
        .track_symbol(Some("─"))
        .thumb_symbol("█")
        .style(Style::default().fg(fg));
    f.render_stateful_widget(
        scrollbar,
        area.inner(Margin { horizontal: 1, vertical: 0 }),
        &mut scroll_state,
    );
}
