# PLAN — Cyberpunk Aesthetic Overhaul: Main Menu

> **Objetivo:** Transformar el menú principal y pantalla de splash de `rinthel_tui`
> con efectos visuales cyberpunk avanzados sin romper la funcionalidad existente.
>
> **Stack actual:** Textual (Python), CSS propio (`rinthel.tcss`), paleta canónica
> (`palette.py`), 8 efectos de transición (`transitions.py`), 3 efectos de texto
> (`flicker.py`).

---

## ⚠️ Notas de investigación — Textual docs oficiales

**Fuente:** https://textual.textualize.io/guide/styles/ · https://textual.textualize.io/widgets/option_list/ · https://textual.textualize.io/guide/animation/

1. **`box-shadow` → NO SOPORTADO.** Textual no tiene `box-shadow` como propiedad CSS. Confirmado en GitHub discussions (#4034). Alternativa para glow: alternar `border-color` + `border` con timer Python (`set_interval`).
2. **`@keyframes` → NO SOPORTADO en CSS de Textual.** Las animaciones en Textual son puramente Python vía `styles.animate()`. No hay motor de CSS keyframes. Para animaciones repetitivas (pulsing glow), usar `set_interval` en Python.
3. **Clases de OptionList:** Los nombres del plan eran incorrectos. Las clases reales (BEM-style) son:
   - `option-list--option` — opción normal (no disabled, no highlighted, sin hover)
   - `option-list--option-highlighted` — la opción actualmente seleccionada/focuseada (reemplaza `option--focused`)
   - `option-list--option-hover` — opción con mouse encima (reemplaza `.option:hover`)
   - `option-list--option-disabled` — opción deshabilitada
   - `option-list--separator` — separadores
4. **Textual no tiene `position: absolute`.** Alternativa para esquinas decorativas: Grid 3x3.
5. **Textual no tiene `z-index`.** Apilamiento por orden de `compose()`.
6. **Sistema de animación:** Python-only (`widget.styles.animate(prop, value, duration)`). No hay CSS `@keyframes`, `animation`, ni pseudo-elementos `::before`/`::after`.

---

## Recomendaciones de implementación (aprobadas)

1. ✅ Revisar docs oficiales de Textual antes de implementar cada fase.
2. ✅ Investigar a fondo cuando lleguemos a cada fase problemática.
3. ~~Fase 4 (esquinas ASCII)~~ → **Omitida**. No aporta suficiente valor vs el esfuerzo de reestructurar el layout con Grid 3x3.
4. ✅ Confirmar clases CSS de Textual con la versión instalada antes de Fase 5.
5. ✅ El HUD footer (Fase 6) reutiliza el watcher de CPU/RAM ya existente en `MonitorScreen` — adaptar el `_poll_cpu()` worker para alimentar también un sparkline en el menú.
6. ✅ Para scanlines de fondo: widget estático de fondo a pantalla completa con opacidad baja, colocado antes que el menú en `compose()`. Sin z-index (no soportado).
7. ✅ No cambiar la estructura principal del programa. Mantener `OptionList` y su navegación nativa.
8. ✅ Variables de configuración via env vars (`RINTHEL_EFFECTS=off`, etc.) en vez de modificar el dataclass frozen.

---

## Resumen de dependencias entre fases

```
Fase 1 (glow border) ──→ Fase 5 (focus highlight) ──→ Fase 6 (HUD footer)
     │                              │
     └──→ Fase 2 (glitch title) ───┘
          │
          ├──→ Fase 3 (dividers)
          ├──→ Fase 7 (scanlines ambient)
          └──→ Fase 9 (splash ripple)
```

---

## Criterios de aceptación general

1. **Ningún cambio funcional:** los botones del menú siguen haciendo exactamente lo mismo.
2. **Performance:** el menú debe cargar en < 200ms (animaciones no bloqueantes).
3. **Terminal compatibility:** todo debe funcionar en terminales ANSI estándar sin
   dependencias de colores truecolor (la paleta actual ya usa hex que Textual mapea).
4. **Configuración:** los efectos visuales deben poder desactivarse con variables de
   entorno (`RINTHEL_EFFECTS=off`) para terminales lentos o CI.

---

## Fase 1 — Glow pulsante en borde del menú (Python timer)

**Archivo:** `rinthel_tui/tui/screens/menu.py`

### Qué cambia
- Se agrega un timer en `MenuScreen.on_mount()` que alterna el `border-color` y
  `border` de `#menu-box` entre dos estados: magenta estático y cyan con borde doble.
- **NO usar CSS @keyframes ni box-shadow** (no soportados por Textual).

### Estrategia
- En `on_mount()`, crear un `set_interval(1.5, self._pulse_border)` que alterne
  entre los dos estados del borde.
- Estado A: `self.query_one("#menu-box").styles.border = ("solid", "$accent")`
- Estado B: `self.query_one("#menu-box").styles.border = ("double", "$fg")`

### Código aproximado

```python
def on_mount(self) -> None:
    self._glow_enabled = CONFIG.effects_enabled
    if self._glow_enabled:
        self.set_interval(1.5, self._pulse_border)
        self._border_state = "magenta"

def _pulse_border(self) -> None:
    box = self.query_one("#menu-box")
    if self._border_state == "magenta":
        box.styles.border = ("double", "$fg")  # cyan border
        self._border_state = "cyan"
    else:
        box.styles.border = ("solid", "$accent")  # magenta border
        self._border_state = "magenta"
```

### CSS adicional (solo para el glow inset, sin box-shadow)

Opcional en `rinthel.tcss`:
```css
#menu-box {
    /* border se controla por Python timer */
}
```

### Riesgos
- Mínimo. Solo timer Python sobre estilos existentes.
- Si `RINTHEL_EFFECTS=off`, el timer no se activa.

---

## Fase 2 — Glitch reveal en título del menú

**Archivos:** `rinthel_tui/tui/screens/menu.py` + `rinthel_tui/tui/effects/flicker.py` (ya existe)

### Qué cambia
- El `Static("◈ RINTHEL.AI -- NIGHT CITY COMMAND TERMINAL")` se reemplaza por un
  `GlitchLabel` con `frames=12` y `frame_ms=50`.
- Se mantiene la clase `menu-title` para conservar el color magenta.

### Código nuevo en `compose()`

```python
from rinthel_tui.tui.effects.flicker import GlitchLabel

# Reemplazar:
# yield Static("◈ RINTHEL.AI -- NIGHT CITY COMMAND TERMINAL", classes="menu-title")
# Por:
yield GlitchLabel(
    "◈ RINTHEL.AI -- NIGHT CITY COMMAND TERMINAL",
    frames=12, frame_ms=50,
    classes="menu-title", id="menu-title"
)
```

### CSS adicional (opcional, para centrar el GlitchLabel)

```css
#menu-title {
    text-align: center;
    width: 100%;
}
```

### Riesgos
- `GlitchLabel` hereda de `Static`, no debería romper layout. El timer interno se
  limpia al terminar la animación.

---

## Fase 3 — Separadores temáticos entre opciones del menú

**Archivos:** `rinthel_tui/tui/screens/menu.py`

### Qué cambia
- Se agregan divisores ASCII temáticos entre grupos de opciones usando el widget
  `Separator` de Textual (soportado nativamente por `OptionList`).

### Estrategia: Usar `Separator` con texto custom

Textual soporta `Separator` dentro de `OptionList` para insertar líneas divisoras.
Se puede crear un separador con caracteres temáticos:

```python
from textual.widgets.option_list import Separator

_DIVIDER_1 = Separator("⊹───◆───∴")
_DIVIDER_2 = Separator("⊛───▓───⌇")
_DIVIDER_3 = Separator("◈───▲───∷")
```

### Código en `_OPTIONS`

```python
_OPTIONS = (
    "[1] BOOT        -- Levantar todo (up)",
    "[2] RELOAD      -- Apagar + reiniciar completo",
    _DIVIDER_1,
    "[3] TERMINATE   -- Shutdown total",
    "[4] LOGS        -- Ver llama-server en vivo",
    _DIVIDER_2,
    "[5] CAPTURE     -- Capturar perfil MoE (routing profile)",
    "[6] MONITOR     -- Estado de servicios/Docker/GPU/CPU",
    _DIVIDER_3,
    "[7] EXIT        -- Cerrar terminal",
)
```

### CSS para los separadores

```css
#menu-options .option-list--separator {
    color: $dim;
}
```

### Riesgos
- Bajo. `Separator` es nativo de Textual. Verificar que los caracteres Unicode
  se rendericen correctamente en el terminal objetivo.

---

## ~~Fase 4 — Decoración ASCII en esquinas del menú~~

> **Omitida.** Requiere reestructurar todo el layout del menú-box con Grid 3x3,
> lo cual viola la recomendación #7 (no cambiar la estructura principal).
> Se puede agregar como feature futura si se decide refactorizar el layout.

---

## Fase 5 — Focus highlight custom en OptionList

**Archivo:** `rinthel_tui/theme/rinthel.tcss`

### Qué cambia
- Se customiza el estilo del item seleccionado/focado en `#menu-options`.
- Reverse-video (fondo magenta, texto negro) + bold.

### CSS nuevo (clases CORRECTAS de Textual docs)

```css
/* Clase oficial: option-list--option-highlighted (no "option--focused") */
#menu-options .option-list--option-highlighted {
    background: $accent;
    color: $background;
    text-style: bold;
}

/* Clase oficial: option-list--option-hover (no ".option:hover") */
#menu-options .option-list--option-hover {
    background: $electric-dim;
    color: $primary;
}
```

### Nota sobre variables CSS personalizadas
Textual no tiene `$accent-dim` por defecto. Se agrega en Fase 10:

```python
# cyberpunk_theme.py → variables dict
"accent-dim": palette.ACCENT + "40",  # alpha 25% hex
```

### Riesgos
- Las clases de OptionList pueden variar entre versiones de Textual.
- **Verificar con `pip show textual` la versión instalada y contrastar con**
  https://textual.textualize.io/widgets/option_list/#component-classes antes de implementar.
- En la versión actual (docs 2024/2025), las clases son:
  `option-list--option`, `option-list--option-disabled`,
  `option-list--option-highlighted`, `option-list--option-hover`,
  `option-list--separator`.

---

## Fase 6 — HUD footer (hora + sparkline mini)

**Archivos:** `rinthel_tui/tui/screens/menu.py` + `rinthel_tui/theme/rinthel.tcss`

### Qué cambia
- El `#menu-footer` pasa de solo badges a un layout horizontal con:
  - Izquierda: badges (Understory, Pithagoras) — existente
  - Centro: hora del sistema en formato cyberpunk (`2087-09-02 03:42:17`)
  - Derecha: sparkline mini de CPU (reusa `Sparkline` widget, 15 muestras)

### Widget de hora propuesto
Nuevo widget `CyberClock(Static)` que se actualice cada segundo:

```python
class CyberClock(Static):
    """Reloj en tiempo real con formato cyberpunk."""
    
    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)
    
    def _tick(self) -> None:
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update(f"⌇ {now} ⌇")
```

### Sparkline mini — Reutilizar watcher de MonitorScreen
El `MonitorScreen` ya tiene un `_poll_cpu()` worker que alimenta `cpu_sparkline`.
Para el menú, se crea un Sparkline independiente con `maxlen=15`:

```python
self.menu_cpu_sparkline = Sparkline(id="menu-cpu-sparkline", maxlen=15)
```

Se puede reutilizar la función `resources.read_cpu_ram()` de MonitorScreen
creando un worker ligero en el menú.

### CSS nuevo

```css
#menu-footer {
    height: 2;  /* subir de 1 a 2 filas */
    dock: bottom;
    color: $dim;
    background: $surface;
}
```

### Riesgos
- `Sparkline` puede necesitar ajustes para renderizado mini. El `CyberClock` es trivial.
- Reutilizar el watcher de CPU sin duplicar polling excesivo.

---

## Fase 7 — Scanlines ambientales de fondo

**Archivos:** `rinthel_tui/tui/screens/menu.py` + `rinthel_tui/theme/rinthel.tcss`

### Qué cambia
- Se agrega un widget de scanlines CRT sutiles como fondo permanente detrás del menú.
- Diferente de Fase 1 que solo se activa al seleccionar opciones.

### Estrategia: Widget estático a pantalla completa con opacidad baja

Colocar el widget de scanlines **primero** en `compose()` (antes del menu-box)
para que quede "detrás" visualmente. Sin z-index (no soportado).

```python
class AmbientScanlines(Static):
    """Scanlines CRT sutiles como fondo permanente."""
    
    def __init__(self) -> None:
        super().__init__("", id="ambient-scanlines")
        self._timer = None
    
    def on_mount(self) -> None:
        self.set_interval(0.1, self._refresh)
    
    def _refresh(self) -> None:
        # Generar patrón de líneas horizontales alternadas
        lines = []
        for i in range(self.size.height):
            if i % 2 == 0:
                lines.append("─" * self.size.width)
            else:
                lines.append(" " * self.size.width)
        self.update("\n".join(lines))
```

### CSS

```css
#ambient-scanlines {
    color: $cool-dim;
    opacity: 0.15;
    dock: bottom;
}
```

### Riesgos
- Actualizar un Static cada 100ms puede causar parpadeo visible en terminales lentos.
- Se debe verificar con `RINTHEL_EFFECTS=off` que no se monte.
- **Nota:** Este widget podría consumar CPU innecesaria. Considerar aumentar el
  intervalo a 200-300ms o usar un patrón estático sin refresh continuo.

---

## ~~Fase 8 — Animación escalonada de opciones al entrar~~

> **Omitida.** Reemplazar `OptionList` por labels individuales violaría la
> recomendación #7 (no cambiar la estructura principal). El plan original lo
> marcaba como "cambiante". Se puede implementar como feature futura si se
> refactoriza el menú completo.

---

## Fase 9 — Splash screen: efecto de apertura con ripple

**Archivos:** `rinthel_tui/tui/screens/splash.py` + `rinthel_tui/tui/effects/transitions.py` (ya existe `RippleEffect`)

### Qué cambia
- Antes de que aparezca el banner animado, se muestra un breve `RippleEffect`
  (anillos concéntricos expanding) como transición de entrada al splash.
- El prompt "Presiona cualquier tecla..." también recibe `GlitchLabel`.

### Código nuevo en `SplashScreen`

```python
from rinthel_tui.tui.effects.transitions import RippleEffect

async def on_mount(self) -> None:
    if CONFIG.effects_enabled:
        await self.app.push_screen_wait(RippleEffect(count=2, speed_ms=50))
    # ... continuar con el intro animation normal ...
```

### Riesgos
- Agrega ~1.5s adicionales al splash. Configurable via env var `RINTHEL_SPLASH_RIPPLE=false`.

---

## Fase 10 — Paleta extendida: variables CSS para colores dim

**Archivos:** `rinthel_tui/theme/cyberpunk_theme.py` + `rinthel_tui/theme/rinthel.tcss`

### Qué cambia
- Se agregan variables CSS al theme para los colores dim de la paleta extendida,
  permitiendo usar `$accent-dim`, `$cool-dim`, `$hot-dim`, `$electric-dim`,
  `$steel-dim` directamente en el CSS.

### Código nuevo en `cyberpunk_theme.py`

```python
CYBERPUNK_THEME = Theme(
    name="cyberpunk",
    # ... existing ...
    variables={
        "border": palette.FG,
        "caution": palette.CAUTION,
        "dim": palette.DIM,
        # Extended palette como variables CSS
        "accent-dim": "#660066",       # 50% accent
        "cool-dim": palette.COOL_DIM,
        "hot-dim": palette.HOT_DIM,
        "electric-dim": palette.ELECTRIC_DIM,
        "steel-dim": palette.STEEL_DIM,
    },
)
```

### Uso en CSS (todas las fases anteriores)

```css
#menu-options .option-list--option-hover {
    background: $electric-dim;
}

#ambient-scanlines {
    color: $cool-dim;
}
```

### Riesgos
- Ninguno. Son variables adicionales, no afectan el comportamiento existente.

---

## Variables de configuración (env vars)

```bash
# En .env o shell profile:

RINTHEL_EFFECTS=on          # Toggle global de efectos (default: on)
RINTHEL_SPLASH_RIPPLE=on    # Ripple al entrar al splash (default: on)
RINTHEL_HUD_CLOCK=on        # Reloj en el footer del menú (default: on)
```

Implementación en `config.py` o `app.py`:

```python
import os

def _bool_env(name: str, default: bool = True) -> bool:
    val = os.environ.get(name, "").lower()
    if val == "":
        return default
    return val in ("1", "on", "true", "yes")

EFFECTS_ENABLED = _bool_env("RINTHEL_EFFECTS", True)
SPLASH_RIPPLE = _bool_env("RINTHEL_SPLASH_RIPPLE", True)
HUD_CLOCK = _bool_env("RINTHEL_HUD_CLOCK", True)
```
