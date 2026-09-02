"""Registro del Theme nativo de Textual a partir de la paleta cyberpunk."""

from textual.theme import Theme

from rinthel_tui.theme import palette

CYBERPUNK_THEME = Theme(
    name="cyberpunk",
    primary=palette.FG,
    secondary=palette.ELECTRIC,
    accent=palette.ACCENT,
    warning=palette.WARN,
    error=palette.HOT,
    success=palette.SUCCESS,
    foreground=palette.GLOW,
    background=palette.BG,
    surface=palette.BG,
    panel=palette.DIM,
    dark=True,
    variables={
        "border": palette.FG,
        "caution": palette.CAUTION,
        "dim": palette.DIM,
        # Extended palette — variables CSS reutilizables por tui screens
        "accent-dim": palette.ACCENT_DIM,
        "cool-dim": palette.COOL_DIM,
        "hot-dim": palette.HOT_DIM,
        "electric-dim": palette.ELECTRIC_DIM,
        "steel-dim": palette.STEEL_DIM,
    },
)
