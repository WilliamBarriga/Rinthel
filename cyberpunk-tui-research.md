# Cyberpunk TUI — Investigación y Plan de Retoma

> Rama: `cyberpunk-tui-research`
> Estado: Investigación completada. Pendiente implementación.

## Contexto

Se necesita una TUI con **personalización máxima** de cada widget y pantalla, estilo cyberpunk. Textual fue descartado por sus limitaciones: CSS propio limitado, sin overlays/libre superposición de widgets, y sistema de estilos poco flexible.

## Stack Recomendado

```
Ratatui + crossterm + ratatui-style + ratatui-sci-fi
```

| Componente | Propósito |
|---|---|
| **Ratatui** (Rust) | Motor frame-by-frame, control absoluto sobre cada celda |
| **crossterm** | Backend: raw mode, alternate screen, mouse, truecolor |
| **ratatui-style** | CSS cascade real con variables, selectores, pseudo-states |
| **ratatui-sci-fi** | 72 widgets cyberpunk/sci-fi listos para usar |

### ¿Por qué este stack?

- Control total sobre cada caracter/píxel de la pantalla
- Sin restricciones de layout ni capas limitadas
- CSS cascade real (no un dialecto propio como `.tcss` de Textual)
- Widgets especializados: radar, matrix rain, glitch text, scanlines, oscilloscope, spectrum bars, activity rings, star map, noise, boot sequence, comm log con markdown
- 8 temas predefinidos: Cyberpunk, Fallout, Weyland, Deep Space, Bloodmoon, Nebula, Arctic, Sentinel
- Imágenes reales en terminal vía ratatui-image + protocolo Kitty/Sixel
- Audio sintetizado opcional (6 efectos via rodio)
- Binario estático, zero dependencias, performance brutal

## Links Clave

### Stack principal
- Ratatui — https://github.com/ratatui/ratatui
- crossterm — https://github.com/crossterm-rs/crossterm
- ratatui-style — https://github.com/liangdi/ratatui-style
- ratatui-sci-fi — https://github.com/Liangdi/ratatui-sci-fi

### Imágenes en terminal
- ratatui-image — https://github.com/ratatui/ratatui-image

### Editor visual
- TUIStudio (Figma-like para TUIs) — https://tui.studio / https://github.com/jalonsogo/tui-studio

### Terminal emulators recomendados
- WezTerm — https://wezfurlong.org/wezterm/
- Kitty — https://sw.kovidgoyal.net/kitty/
- Ghostty — https://ghostty.org/

### Protocolo de gráficos de Kitty
- Spec — https://sw.kovidgoyal.net/kitty/graphics-protocol/

### Ejemplo Sci-Fi HUD con ratatui-style
- 07_scifi_hud.rs — https://docs.rs/crate/ratatui-style/latest/source/examples/07_scifi_hud.rs

### Comparativa completa TUI 2026
- TUI Renaissance deep dive — https://www.youngju.dev/blog/culture/2026-05-14-tui-development-ratatui-bubbletea-ink-textual-terminal-ui-renaissance-deep-dive-2026.en

## Widgets Clave de ratatui-sci-fi

| Widget | Descripción |
|---|---|
| `SciFiRadar` | Radar animado con sweep rotatorio |
| `MatrixRain` | Lluvia de caracteres estilo Matrix |
| `GlitchText` | Texto con efecto glitch/corruption |
| `ScanlineOverlay` | Overlay de scanlines CRT |
| `Oscilloscope` | Osciloscopio en tiempo real |
| `SpectrumBars` | Barras de espectro audio visualizer |
| `ActivityRings` | Anillos de actividad |
| `StarMap` | Mapa estelar |
| `Noise` | Ruido visual estático |
| `BootSequence` | Secuencia de arranque retro |
| `CommLog` | Chat con markdown + streaming character-by-character |
| `AlertPopup` | Popup de alerta con borde rojo parpadeante |
| `EnergyGauge` | Barra de energía tipo reactor |
| `TargetLock` | Contenedor HUD con crosshair |
| `BiometricChart` | Gráfico de signos vitales |

## Alternativas Consideradas

| Framework | Lenguaje | Veredicto |
|---|---|---|
| Textual | Python | ❌ CSS limitado, overlays restringidos |
| RunTUI | Python | ⚠️ Ventanas flotantes útiles pero menos control fino |
| Bubble Tea + Lipgloss | Go | ⚠️ Muy pulido pero menos widgets especializados |
| Ink | Node.js/TS | ⚠️ Heavy runtime, más orientado a CLI wizards |
| PyRatatui | Python (PyO3) | ✅ Opción si se necesita Python con backend Rust |

## Pasos para Implementar

1. Crear proyecto Rust con `cargo new`
2. Añadir dependencias: `ratatui`, `crossterm`, `ratatui-style`, `ratatui-sci-fi`
3. Configurar tema Cyberpunk por defecto
4. Crear layout base con paneles (sidebar, main area, status bar)
5. Integrar widgets cyberpunk (radar, gauges, event log)
6. Agregar ratatui-image para imágenes si se requiere
7. Probar en Kitty/WezTerm/Ghostty para máximo efecto visual

## Notas

- El repo actual (`Rinthel-general`) tiene un `tui/__init__.py` vacío en `graphify-vault/`. No está relacionado con esta investigación.
- Tarkark ejecuta en `pithagoras` container sin acceso a Docker host. Cualquier build Rust se hace dentro del container o se pide ejecución en host.
