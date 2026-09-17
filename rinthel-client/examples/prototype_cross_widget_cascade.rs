//! PROTOTYPE — ticket 10 (wayfinder: Ratatui TUI Migration).
//! Ver .scratch/ratatui-migration/issues/10-cross-widget-cascade-prototype.md
//!
//! PREGUNTA QUE ESTE PROTOTIPO RESPONDE:
//! ¿Puede UNA sola regla CSS de `ratatui-style` apuntar a la vez a dos
//! widgets custom distintos (`ServiceBadge` y `JackInOptionList`), vía un
//! ancestro común (`StatusPanel`), de forma que cambiar de tema mueva el
//! estilo de los dos juntos? Clases aisladas por widget sin selector
//! compartido NO cuenta como resuelto (ver ticket 10).
//!
//! El research del ticket 09 confirmó por separado: combinador de
//! descendencia (`A B`, ejemplo `03_cascade.rs` del propio crate) y
//! comma-list (`A, B`, tests unitarios de `selector.rs`). Lo que NADIE
//! probó en un programa real es la combinación de ambos a la vez:
//!
//!     StatusPanel ServiceBadge, StatusPanel JackInOptionList { ... }
//!
//! Eso es exactamente lo que este prototipo ejercita en vivo.
//!
//! No hace falta el daemon spike corriendo — esto es standalone.
//!
//! Corré:
//!   cargo run --example prototype_cross_widget_cascade
//!
//! Teclas: ↑/↓ mueve la selección de la lista · t cicla de tema · q sale.

use std::io;
use std::time::Duration;

use crossterm::event::{self, Event, KeyCode};
use crossterm::execute;
use crossterm::terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen};
use ratatui::backend::CrosstermBackend;
use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::Modifier;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph};
use ratatui::{Frame, Terminal};
use ratatui_style::{CascadeContext, OwnedNode, Stylesheet};

/// La regla bajo prueba. Un solo bloque de declaración, un selector con
/// comma-list de dos ramas, cada rama con combinador de descendencia sobre
/// el mismo ancestro (`StatusPanel`). Constante para poder mostrarla en
/// pantalla tal cual se está evaluando, no solo en el código.
const SHARED_RULE: &str = "StatusPanel ServiceBadge, StatusPanel JackInOptionList { color: var(--accent); background: var(--panel-bg); }";

/// Los tres temas contrastantes que pide el ticket 10. Cada uno redefine
/// los mismos tokens (`--accent`/`--panel-bg`/`--offline`); la regla
/// compartida de arriba no cambia entre temas — solo lo que resuelve `var()`.
struct ThemeDef {
    name: &'static str,
    css: &'static str,
}

const THEMES: [ThemeDef; 3] = [
    ThemeDef {
        name: "Cyberpunk",
        css: r"
            :root { --accent: #00eaff; --panel-bg: #10131a; --offline: #ff2b6d; }
        ",
    },
    ThemeDef {
        name: "Arctic",
        css: r"
            :root { --accent: #4fb2e8; --panel-bg: #e8f1f7; --offline: #c23b3b; }
        ",
    },
    ThemeDef {
        name: "Solar",
        css: r"
            :root { --accent: #d99a2b; --panel-bg: #1c1712; --offline: #8a3b1f; }
        ",
    },
];

/// Arma el stylesheet completo del tema `idx`: sus tokens `:root` + la
/// regla compartida bajo prueba + un override por clase (`.offline`) que
/// demuestra que el selector compartido convive con una regla más
/// específica sin romperse.
fn build_sheet(theme_idx: usize) -> Stylesheet {
    let css = format!(
        "{}\n{}\nStatusPanel ServiceBadge.offline {{ color: var(--offline); }}",
        THEMES[theme_idx].css, SHARED_RULE
    );
    Stylesheet::parse(&css).expect("CSS del prototipo inválido")
}

struct ServiceBadge {
    label: &'static str,
    online: bool,
}

impl ServiceBadge {
    fn node(&self) -> OwnedNode {
        let class = if self.online { "online" } else { "offline" };
        OwnedNode::new("ServiceBadge").with_classes([class])
    }
}

struct JackInOptionList {
    items: [&'static str; 4],
    selected: usize,
}

impl JackInOptionList {
    fn node(&self) -> OwnedNode {
        OwnedNode::new("JackInOptionList")
    }
}

/// Corre el walk del cascade (StatusPanel > los dos widgets) para el tema
/// `theme_idx` y devuelve los tres `Style` resueltos. Aislado de `draw()`
/// para poder llamarlo también desde `--check` sin terminal.
fn resolve(theme_idx: usize, list: &JackInOptionList) -> (ratatui::style::Style, ratatui::style::Style, ratatui::style::Style) {
    let sheet = build_sheet(theme_idx);
    let mut ctx = CascadeContext::new(&sheet);

    // Ancestro común — ninguna regla lo estiliza directamente, solo agrupa
    // a los dos widgets bajo el combinador de descendencia.
    let panel_node = OwnedNode::new("StatusPanel");
    ctx.enter(&panel_node);

    let badge_online = ServiceBadge { label: "understory", online: true };
    let badge_offline = ServiceBadge { label: "pithagoras", online: false };

    let online_computed = ctx.enter(&badge_online.node());
    ctx.leave();
    let offline_computed = ctx.enter(&badge_offline.node());
    ctx.leave();
    let list_computed = ctx.enter(&list.node());
    ctx.leave();

    ctx.leave(); // StatusPanel

    (online_computed.to_style(), offline_computed.to_style(), list_computed.to_style())
}

fn draw(f: &mut Frame, theme_idx: usize, list: &JackInOptionList) {
    let (online_style, offline_style, list_style) = resolve(theme_idx, list);
    let badge_online = ServiceBadge { label: "understory", online: true };
    let badge_offline = ServiceBadge { label: "pithagoras", online: false };

    // Verificación explícita del criterio de éxito del ticket 10: los dos
    // widgets bajo la regla compartida deben resolver EXACTAMENTE el mismo
    // color, y moverse juntos al cambiar `theme_idx`. El badge offline usa
    // la regla más específica (`.offline`) y por eso debe DIFERIR — eso
    // prueba que el selector compartido convive con un override normal.
    let shared_matches = online_style.fg == list_style.fg;
    let override_differs = online_style.fg != offline_style.fg;
    let verdict = if shared_matches && override_differs {
        Span::styled(
            " ✓ ServiceBadge y JackInOptionList comparten color vía la regla — override .offline sigue funcionando ",
            ratatui::style::Style::default().fg(ratatui::style::Color::Green),
        )
    } else {
        Span::styled(
            " ✗ el selector compartido NO se comportó como se esperaba — ver detalle abajo ",
            ratatui::style::Style::default().fg(ratatui::style::Color::Red),
        )
    };

    let area = f.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(6), // intro / pregunta
            Constraint::Length(3), // badges (ServiceBadge x2)
            Constraint::Min(6),    // lista (JackInOptionList)
            Constraint::Length(3), // veredicto
            Constraint::Length(3), // hint teclas
        ])
        .split(area);

    let intro = Paragraph::new(vec![
        Line::from(Span::styled(
            "Prototipo — ticket 10: cascade compartido entre widgets custom",
            ratatui::style::Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(format!("Tema activo: {}  (t = siguiente tema)", THEMES[theme_idx].name)),
        Line::from(Span::styled(SHARED_RULE, ratatui::style::Style::default().add_modifier(Modifier::ITALIC))),
    ])
    .block(Block::default().borders(Borders::ALL).title(" pregunta "));
    f.render_widget(intro, rows[0]);

    let badges = Paragraph::new(Line::from(vec![
        Span::raw(" "),
        Span::styled(format!(" {} ONLINE ", badge_online.label), online_style),
        Span::raw("   "),
        Span::styled(format!(" {} OFFLINE ", badge_offline.label), offline_style),
    ]))
    .block(Block::default().borders(Borders::ALL).title(" ServiceBadge (StatusPanel > ServiceBadge) "));
    f.render_widget(badges, rows[1]);

    let items: Vec<ListItem> = list
        .items
        .iter()
        .enumerate()
        .map(|(i, label)| {
            let mut style = list_style;
            if i == list.selected {
                style = style.add_modifier(Modifier::BOLD | Modifier::REVERSED);
            }
            ListItem::new(format!("  {label}")).style(style)
        })
        .collect();
    let list_widget = List::new(items).block(
        Block::default()
            .borders(Borders::ALL)
            .title(" JackInOptionList (StatusPanel > JackInOptionList) "),
    );
    f.render_widget(list_widget, rows[2]);

    let verdict_p = Paragraph::new(Line::from(verdict)).block(Block::default().borders(Borders::ALL));
    f.render_widget(verdict_p, rows[3]);

    f.render_widget(
        Paragraph::new(" ↑↓ = mover selección   t = cambiar tema   q = salir ")
            .block(Block::default().borders(Borders::ALL)),
        rows[4],
    );
}

fn main() -> io::Result<()> {
    if std::env::args().any(|a| a == "--check") {
        return run_check();
    }

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut theme_idx = 0usize;
    let mut list = JackInOptionList { items: ["MONITOR", "BOOT", "TERMINATE", "SALIR"], selected: 0 };

    let result = (|| -> io::Result<()> {
        loop {
            terminal.draw(|f| draw(f, theme_idx, &list))?;

            if event::poll(Duration::from_millis(150))? {
                if let Event::Key(key) = event::read()? {
                    match key.code {
                        KeyCode::Char('q') => break,
                        KeyCode::Char('t') => theme_idx = (theme_idx + 1) % THEMES.len(),
                        KeyCode::Up => list.selected = list.selected.saturating_sub(1),
                        KeyCode::Down => list.selected = (list.selected + 1).min(list.items.len() - 1),
                        _ => {}
                    }
                }
            }
        }
        Ok(())
    })();

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    result
}

/// Modo headless (`--check`, sin raw mode / alt screen): corre la misma
/// resolución de cascade que `draw()` para los 3 temas y verifica el
/// criterio de éxito del ticket 10 por código, no a ojo. Pensado para
/// correr antes de la sesión interactiva con Tarkark.
fn run_check() -> io::Result<()> {
    let list = JackInOptionList { items: ["MONITOR", "BOOT", "TERMINATE", "SALIR"], selected: 0 };
    let mut all_ok = true;

    for (idx, theme) in THEMES.iter().enumerate() {
        let (online, offline, list_style) = resolve(idx, &list);
        let shared_matches = online.fg == list_style.fg;
        let override_differs = online.fg != offline.fg;
        let ok = shared_matches && override_differs;
        all_ok &= ok;
        println!(
            "[{}] tema={:<10} ServiceBadge.online.fg={:?} JackInOptionList.fg={:?} (shared_matches={}) ServiceBadge.offline.fg={:?} (override_differs={})",
            if ok { "PASS" } else { "FAIL" },
            theme.name,
            online.fg,
            list_style.fg,
            shared_matches,
            offline.fg,
            override_differs,
        );
    }

    println!(
        "\nRegla bajo prueba: {SHARED_RULE}\nVeredicto global: {}",
        if all_ok { "VIABLE — el selector combinador + comma-list se resolvió igual en los 3 temas" } else { "NO VIABLE — ver detalle arriba" }
    );

    if !all_ok {
        std::process::exit(1);
    }
    Ok(())
}
