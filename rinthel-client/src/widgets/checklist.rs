//! Checklist de fases — puerto de `rinthel_tui/tui/widgets/checklist.py`
//! (sesión 05 del port-map). A diferencia del original, las filas no se
//! predeclaran: no existe del lado cliente un `boot_phases()`/`down_phases()`
//! propio (ver decisión de sesión 05, port-map.md) — cada fila aparece
//! recién cuando llega su primer evento `phase_status` ("running"), en el
//! orden en que el daemon las va corriendo.
//!
//! `tick_spinner()` del original nunca se llamaba desde ningún lado (grep
//! confirmado en `rinthel_tui/tui/`) — el icono de "running" en Textual
//! quedaba fijo en `FRAME_CHARS[0]` en la práctica. Acá se replica ese
//! comportamiento real (glyph estático), no uno animado que no existía.

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
