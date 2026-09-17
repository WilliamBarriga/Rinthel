//! Tail en vivo de log, como widget reusable — puerto de
//! `rinthel_tui/tui/widgets/log_tail.py`. Antes vivía dibujado inline
//! dentro de `draw_monitor`; ahora lo comparten `screens::monitor` (panel
//! mini) y `screens::logs` (pantalla completa), sin duplicar el recorte de
//! líneas visibles.

use std::collections::VecDeque;

use ratatui::layout::Rect;
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;

pub fn draw(f: &mut Frame, area: Rect, lines: &VecDeque<String>, fg: Color, title: &str) {
    let visible: Vec<Line> = lines
        .iter()
        .rev()
        .take((area.height as usize).saturating_sub(2))
        .rev()
        .map(|l| Line::from(Span::styled(l.clone(), Style::default().fg(fg))))
        .collect();
    let widget = Paragraph::new(visible).block(Block::default().borders(Borders::ALL).title(title));
    f.render_widget(widget, area);
}
