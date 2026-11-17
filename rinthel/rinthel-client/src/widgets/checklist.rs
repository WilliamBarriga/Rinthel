//! Checklist de fases — las filas no se predeclaran: no existe del lado
//! cliente una lista de fases propia, cada fila aparece recién cuando llega
//! su primer evento `phase_status` ("running"), en el orden en que el
//! daemon las va corriendo. El icono de "running" es un glyph estático
//! (sin animación de spinner).

use ratatui::layout::Rect;
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem};
use ratatui::Frame;

use crate::app::Colors;

pub fn draw(f: &mut Frame, area: Rect, rows: &[(String, String)], colors: &Colors) {
    let items: Vec<ListItem> = rows
        .iter()
        .map(|(label, status)| {
            let (icon, color) = match status.as_str() {
                "running" => ("░", colors.warn),
                "done" => ("●", colors.success),
                "error" => ("✖", colors.hot),
                _ => ("○", colors.dim),
            };
            ListItem::new(Line::from(Span::styled(format!("{icon} {label}"), Style::default().fg(color))))
        })
        .collect();
    let widget = List::new(items).block(Block::default().borders(Borders::ALL));
    f.render_widget(widget, area);
}
