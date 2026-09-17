//! Screen de logs — tail en vivo del stream `log_line` (misma conexión
//! `/ws/monitor` que ya alimenta el panel mini de `monitor`), pantalla
//! completa. Puerto de `rinthel_tui/tui/screens/logs.py` (sesión 01).
//! Sin `SignalNoiseEffect` al entrar — el original tampoco lo dispara
//! para esta transición (`menu.py:173-174`), a diferencia de casi todas
//! las demás opciones de menú.

use ratatui::Frame;

use crate::app::App;
use crate::widgets::log_tail;

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    log_tail::draw(f, area, &app.log_lines, app.colors.fg, " ◈ LLAMA-SERVER LOG — q para volver ");
}
