# TODOS — Cyberpunk Menu Aesthetic Overhaul

> **Estado:** ⬜ Pendiente · 🟡 En progreso · ✅ Completado  
> **Depende de:** `PLAN-CYBERPUNK-MENU.md` (detalle técnico completo)
> **Docs verificados:** Textual official docs (2024/2025)

---

## Fase 10 — Paleta extendida como variables CSS
- [x] Agregar variables `accent-dim`, `cool-dim`, `hot-dim`, `electric-dim`, `steel-dim` a `cyberpunk_theme.py`
- [x] Verificar que `rinthel.tcss` las referencia correctamente
- **Estado:** ✅ Completado
- **Archivos:** `theme/cyberpunk_theme.py`
- **Bloquea a:** 1, 5, 7

---

## Fase 1 — Borde pulsante con glow (Python timer)
- [x] Agregar `set_interval()` en `MenuScreen.on_mount()` para alternar `styles.border`
- [x] Implementar `_pulse_border()` que alterna entre magenta estático y cyan doble
- [x] Respetar `RINTHEL_EFFECTS` env var
- **Estado:** ✅ Completado
- **Archivos:** `tui/screens/menu.py`
- **Depende de:** —

---

## Fase 2 — Glitch reveal en título del menú
- [x] Reemplazar `Static("◈ RINTHEL.AI...")` por `GlitchLabel(frames=12, frame_ms=50)` en `menu.py`
- [x] CSS `#menu-title` ya existente en `rinthel.tcss`
- **Estado:** ✅ Completado
- **Archivos:** `tui/screens/menu.py`, `theme/rinthel.tcss`
- **Depende de:** —

---

## Fase 3 — Separadores temáticos entre opciones
- [x] Importar `Option` de `textual.widgets.option_list`
- [x] Crear 3 divisores como opciones disabled con clase `menu-divider`
- [x] Insertar en `_OPTIONS` entre grupos
- [x] Agregar CSS `.menu-divider { color: $dim; }`
- **Nota:** Textual 8.2.8 no tiene `Separator("text")`. Se usaron `Option(disabled=True, classes="menu-divider")`.
- **Estado:** ✅ Completado
- **Archivos:** `tui/screens/menu.py`, `theme/rinthel.tcss`
- **Depende de:** —

---

## ~~Fase 4 — Decoración ASCII en esquinas~~
> **Omitida.** Requiere reestructurar layout con Grid 3x3 (viola recomendación #7).

---

## Fase 5 — Focus highlight custom en OptionList
- [x] Textual 8.2.8 verificado
- [x] Clases confirmadas: `option-list--option-highlighted`, `option-list--option-hover`
- [x] Reglas CSS agregadas con nombres BEM-style correctos
- **Estado:** ✅ Completado
- **Archivos:** `theme/rinthel.tcss`
- **Depende de:** 10

---

## Fase 6 — HUD footer (hora + sparkline mini)
- [ ] Crear widget `CyberClock` que actualice cada segundo con formato `⌇ YYYY-MM-DD HH:MM:SS ⌇`
- [ ] Reutilizar `resources.read_cpu_ram()` para sparkline de CPU en el menú
- [ ] Subir altura del `#menu-footer` a 2 filas
- **Estado:** ⬜ Pendiente
- **Archivos:** `tui/screens/menu.py`, `theme/rinthel.tcss`
- **Depende de:** —

---

## Fase 7 — Scanlines ambientales de fondo
- [ ] Crear widget `AmbientScanlines` con patrón de líneas alternadas
- [ ] Configurar opacidad baja (~0.15) y refresh rate (200-300ms para evitar parpadeo)
- [ ] Colocar primero en `compose()` para apilamiento correcto
- **Estado:** ⬜ Pendiente
- **Archivos:** `tui/screens/menu.py`, `theme/rinthel.tcss`
- **Depende de:** 10

---

## ~~Fase 8 — Animación escalonada de opciones~~
> **Omitida.** Reemplazar OptionList viola recomendación #7. Feature futura.

---

## Fase 9 — Splash screen: efecto ripple de apertura
- [ ] Insertar `RippleEffect(count=2, speed_ms=50)` como transición antes del banner en `splash.py`
- [ ] Aplicar `GlitchLabel` al prompt "Presiona cualquier tecla..."
- [ ] Respetar `RINTHEL_SPLASH_RIPPLE` env var
- **Estado:** ⬜ Pendiente
- **Archivos:** `tui/screens/splash.py`, `config.py` o `app.py`
- **Depende de:** —

---

## Env vars (implementación transversal)
- [ ] Agregar `_bool_env()` helper en config/app
- [ ] Variables: `RINTHEL_EFFECTS`, `RINTHEL_SPLASH_RIPPLE`, `RINTHEL_HUD_CLOCK`
- [ ] Documentar en README o .env.example

---

## Checklist global

- [ ] Todas las fases implementadas y probadas
- [ ] Variables de entorno desactivan efectos correctamente
- [ ] No hay regresión funcional en el menú (botones 1-7 funcionan igual)
- [ ] Performance: carga del menú < 200ms
- [ ] Compatible con terminales ANSI estándar
- [ ] Commit separado por fase para fácil revert
