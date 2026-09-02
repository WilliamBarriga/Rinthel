"""Banner "Rinthel.Ai" en duotono — reemplaza show-rinthel-banner.sh.

Mismo estilo que ~/.pi/agent/extensions/cyberpunk-welcome.ts: amarillo neón
para la cara iluminada (los trazos "/", "|", "╱" del arte), morado eléctrico
para la cara en sombra (el resto) y el marco.
"""

from pathlib import Path

from rich.text import Text

from rinthel_tui.theme import palette

BANNER_FILE = Path(__file__).parent / "rinthel-banner.txt"
MAIN_TEXT = "All those moments will be lost in time, like tears in the rain. Time to die."

_LIT_CHARS = frozenset("/|╱")


def _quote_lines(text: str) -> list[str]:
    # Igual que el bash: corta la cita en la primera coma en vez de envolver
    # por ancho.
    first, _, rest = text.partition(",")
    return [f"{first},", rest.strip()]


def render_banner() -> Text:
    lines = BANNER_FILE.read_text().rstrip("\n").split("\n")
    width = max(len(line) for line in lines)
    hbar = "═" * (width + 2)

    result = Text()
    result.append(f"╔{hbar}╗\n", style=palette.ELECTRIC)

    for line in lines:
        padded = line.ljust(width)
        result.append("║ ", style=palette.ELECTRIC)
        for ch in padded:
            if ch == " ":
                result.append(" ")
            elif ch in _LIT_CHARS:
                result.append(ch, style=palette.WARN)
            else:
                result.append(ch, style=palette.ELECTRIC)
        result.append(" ║\n", style=palette.ELECTRIC)

    text_lines = _quote_lines(MAIN_TEXT)
    if len(text_lines) == 1:
        result.append("║ ", style=palette.ELECTRIC)
        result.append(" " * width)
        result.append(" ║\n", style=palette.ELECTRIC)

    for tl in text_lines:
        left = (width - len(tl)) // 2
        right = width - len(tl) - left
        result.append("║ ", style=palette.ELECTRIC)
        result.append(" " * left)
        result.append(tl, style=palette.ELECTRIC)
        result.append(" " * right)
        result.append(" ║\n", style=palette.ELECTRIC)

    result.append(f"╚{hbar}╝", style=palette.ELECTRIC)
    return result
