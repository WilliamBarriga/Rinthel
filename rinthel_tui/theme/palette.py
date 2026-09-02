"""Paleta canónica cyberpunk — fuente numérica única.

Portado 1:1 de ``nightcity/clifx/theme/cyberpunk.sh``. Compartida con el
frontend web de Pithagoras vía ``[data-theme="cyberpunk"]`` — no cambiar
estos hex sin actualizar ese lado también.
"""

FG = "#7CFCFF"  # electric cyan
ACCENT = "#EA00D9"  # neon magenta
ELECTRIC = "#BF00FF"  # electric purple
WARN = "#FCEE0A"  # neon yellow
SUCCESS = "#39FF14"  # neon green
HOT = "#FF003C"  # danger red
CAUTION = "#FFB000"  # amber
GLOW = "#FFFFFF"  # bright white
DIM = "#5A5A72"  # dim slate
BG = "#0D0221"  # night city purple-black

FRAME_CHARS = ("░", "▒", "▓", "█", "◈", "◆", "▲", "∷", "∴", "⊹", "⊛", "⌇")

# ── Extended (categoría) — usados por tui/effects/transitions.py ─────
# Portados de la sección "Extended Palette" de cyberpunk.sh: no forman parte
# de los 9 colores canónicos de Fase 1, pero los 8 effect_* de clifx los usan.
COOL = "#0ABDC6"  # cyan — spatial, water, CRT
COOL_DIM = "#044C4F"
HOT_DIM = "#660018"
ELECTRIC_DIM = "#4C0066"
STEEL = "#6E5F96"  # lavender-gray — static, neutral
STEEL_DIM = "#3A186B"
ACCENT_DIM = "#660066"  # 50% ACCENT
