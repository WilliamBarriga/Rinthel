"""Banner "Rinthel.Ai" en duotono, más la animación que lo compone.

Antes eran dos piezas separadas: una animación pyfiglet sin estilo que
armaba "RINTHEL" y, al terminar, un banner estático con caja y cita en un
font distinto. Ahora ambas comparten el mismo arte (este archivo) y la
misma caja/paleta duotono — la animación literalmente arma este banner,
no otro. Mismo estilo que ~/.pi/agent/extensions/cyberpunk-welcome.ts:
amarillo neón para la cara iluminada (los trazos "/", "|", "╱" del arte),
morado eléctrico para la cara en sombra (el resto) y el marco.
"""

import random
from pathlib import Path

from rich.text import Text

from rinthel_tui.theme import palette

BANNER_FILE = Path(__file__).parent / "rinthel-banner.txt"
MAIN_TEXT = "All those moments will be lost in time, like tears in the rain. Time to die."

_LIT_CHARS = frozenset("/|╱")
_NOISE_CHARS = "░▒▓█╳"


def _quote_lines(text: str) -> list[str]:
    # Igual que el bash: corta la cita en la primera coma en vez de envolver
    # por ancho.
    first, _, rest = text.partition(",")
    return [f"{first},", rest.strip()]


def _art_lines() -> list[str]:
    lines = BANNER_FILE.read_text().rstrip("\n").split("\n")
    width = max(len(line) for line in lines)
    return [line.ljust(width) for line in lines]


def _render_box(art_lines: list[str], quote_lines: list[str] | None = None) -> Text:
    width = max(len(line) for line in art_lines)
    hbar = "═" * (width + 2)

    result = Text()
    result.append(f"╔{hbar}╗\n", style=palette.ELECTRIC)

    for line in art_lines:
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

    if quote_lines:
        result.append("║ ", style=palette.ELECTRIC)
        result.append(" " * width)
        result.append(" ║\n", style=palette.ELECTRIC)

        for tl in quote_lines:
            left = (width - len(tl)) // 2
            right = width - len(tl) - left
            result.append("║ ", style=palette.ELECTRIC)
            result.append(" " * left)
            result.append(tl, style=palette.ELECTRIC)
            result.append(" " * right)
            result.append(" ║\n", style=palette.ELECTRIC)

    result.append(f"╚{hbar}╝", style=palette.ELECTRIC)
    return result


def render_banner() -> Text:
    return _render_box(_art_lines(), _quote_lines(MAIN_TEXT))


# ── Animación de composición ──────────────────────────────────────────
# Mismo algoritmo que tools/gen_rinthel_intro.py (noise -> reveal ->
# stable-flicker) pero corriendo sobre el arte de este banner en vez de
# un render pyfiglet aparte, y devolviendo cajas ya coloreadas en vez de
# texto plano — cada frame es un paso más hacia render_banner().

_NOISE_FRAMES = 4
_REVEAL_FRAMES = 9
_STABLE_FRAMES = 4


def _noise_char() -> str:
    return random.choice(_NOISE_CHARS)


def _noise_row(width: int, density: float = 0.9) -> str:
    return "".join(_noise_char() if random.random() < density else " " for _ in range(width))


def _frame_noise(width: int, height: int) -> list[str]:
    return [_noise_row(width) for _ in range(height)]


def _frame_reveal(clean: list[str], width: int, step: int, total_steps: int) -> list[str]:
    """step es 1-indexado en [1, total_steps]; el reveal crece izq->der."""
    threshold = width * step / total_steps
    edge_band = max(2, width // 12)  # banda glitchy justo en el borde del wipe
    out_lines = []
    for row in clean:
        chars = []
        for x, ch in enumerate(row):
            if x < threshold - edge_band:
                chars.append(ch)
            elif x < threshold:
                chars.append(ch if random.random() < 0.25 else _noise_char())
            else:
                chars.append(_noise_char() if random.random() < 0.55 else " ")
        out_lines.append("".join(chars))
    return out_lines


def _frame_stable(clean: list[str], glitch_count: int) -> list[str]:
    height = len(clean)
    width = len(clean[0]) if clean else 0
    grid = [list(row) for row in clean]
    ink_cells = [(y, x) for y in range(height) for x in range(width) if grid[y][x] != " "]
    for y, x in random.sample(ink_cells, min(glitch_count, len(ink_cells))):
        grid[y][x] = _noise_char()
    return ["".join(row) for row in grid]


def compose_frames(
    *, noise_frames: int = _NOISE_FRAMES, reveal_frames: int = _REVEAL_FRAMES, stable_frames: int = _STABLE_FRAMES
) -> list[Text]:
    """Frames (ya renderizados como caja duotono) que arman este banner
    desde ruido hasta el arte limpio, con flicker leve al final."""
    clean = _art_lines()
    width = max(len(line) for line in clean)
    height = len(clean)

    raw_frames: list[list[str]] = []
    for _ in range(noise_frames):
        raw_frames.append(_frame_noise(width, height))
    for i in range(1, reveal_frames + 1):
        raw_frames.append(_frame_reveal(clean, width, i, reveal_frames))
    raw_frames.append(clean)
    for _ in range(stable_frames - 1):
        raw_frames.append(_frame_stable(clean, glitch_count=2))

    return [_render_box(frame) for frame in raw_frames]
