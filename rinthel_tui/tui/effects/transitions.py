"""Los 8 effect_* de clifx/scripts/manifest_{corruption,atmosphere,spatial}.sh
que Rinthel realmente usa. La matemática generativa de cada uno se porta
casi 1:1 (no gana nada reinventada); lo que cambia es el renderizado:
en vez de move_cursor absoluto + printf sobre el terminal, cada frame arma
una grilla (char, Style) completa que TransitionEffect convierte a Strip.
"""

import asyncio
import random

from rich.style import Style

from rinthel_tui.theme import palette
from rinthel_tui.tui.effects.base import Grid, TransitionEffect, blank_grid, grid_to_strips

def _deadline(seconds: float) -> float:
    return asyncio.get_event_loop().time() + seconds


def _now() -> float:
    return asyncio.get_event_loop().time()


# ── manifest_corruption.sh ────────────────────────────────────


class ScreenTearEffect(TransitionEffect):
    """Bandas horizontales desplazadas — GPU artifacts / VHS tracking."""

    def __init__(self, duration: float = 2.0, intensity: int = 3) -> None:
        super().__init__()
        self.duration = duration
        self.intensity = max(1, intensity)

    async def run(self, width: int, height: int) -> None:
        style = Style(color=palette.HOT_DIM)
        end = _deadline(self.duration)
        while _now() < end:
            grid = blank_grid(width, height)
            bands = random.randint(1, self.intensity)
            for _ in range(bands):
                row = random.randrange(max(1, height))
                spread = self.intensity * 2
                offset = random.randint(-spread, spread) or random.choice([-1, 1])
                line = grid[row]
                if offset > 0:
                    for c in range(offset, width):
                        ch = random.choice(palette.FRAME_CHARS) if random.random() < 0.5 else " "
                        line[c] = (ch, style)
                else:
                    abs_off = -offset
                    for c in range(max(0, width - abs_off)):
                        ch = random.choice(palette.FRAME_CHARS) if random.random() < 0.5 else " "
                        line[c] = (ch, style)
            self.set_frame(grid_to_strips(grid))
            await asyncio.sleep(0.04 / self.intensity)
            self.clear()
            await asyncio.sleep(0.02 / self.intensity)


class ScanlinesEffect(TransitionEffect):
    """Barrido de scanlines CRT, ida y vuelta."""

    def __init__(self, duration: float = 3.0, speed_ms: int = 20) -> None:
        super().__init__()
        self.duration = duration
        self.speed = speed_ms / 1000

    async def run(self, width: int, height: int) -> None:
        dim = Style(color=palette.COOL_DIM)
        bright = Style(color=palette.COOL)
        end = _deadline(self.duration)
        while _now() < end:
            grid = blank_grid(width, height)
            for row in range(0, height, 2):
                grid[row] = [("─", dim) for _ in range(width)]
                self.set_frame(grid_to_strips(grid))
                await asyncio.sleep(self.speed)
            await asyncio.sleep(0.1)
            self.clear()
            await asyncio.sleep(0.2)

            grid = blank_grid(width, height)
            for row in range(height - 1, -1, -2):
                grid[row] = [
                    ("─", bright if random.random() < 0.125 else dim) for _ in range(width)
                ]
                self.set_frame(grid_to_strips(grid))
                await asyncio.sleep(self.speed)
            await asyncio.sleep(0.1)
            self.clear()
            await asyncio.sleep(0.15)


class ChromaticAberrationEffect(TransitionEffect):
    """Separación RGB — capas roja/verde/azul jitterean por separado."""

    def __init__(self, text: str = "SIGNAL LOST", duration: float = 2.0) -> None:
        super().__init__()
        self.text = text
        self.duration = duration

    @staticmethod
    def _place(grid: Grid, row: int, col: int, text: str, style: Style, width: int, height: int) -> None:
        if not (0 <= row < height):
            return
        col = max(0, col)
        for i, ch in enumerate(text):
            c = col + i
            if 0 <= c < width:
                grid[row][c] = (ch, style)

    async def run(self, width: int, height: int) -> None:
        center_row = height // 2
        center_col = max(3, (width - len(self.text)) // 2)
        red = Style(color="#FF0000")
        blue = Style(color="#0087FF")
        green = Style(color=palette.GLOW)
        end = _deadline(self.duration)
        while _now() < end:
            grid = blank_grid(width, height)
            r_offset = random.randint(-1, 1)
            b_offset = random.randint(-1, 1)
            self._place(grid, center_row - 1, center_col + r_offset, self.text, red, width, height)
            self._place(grid, center_row, center_col, self.text, green, width, height)
            self._place(grid, center_row + 1, center_col + b_offset, self.text, blue, width, height)
            self.set_frame(grid_to_strips(grid))
            await asyncio.sleep(0.08)
        self.clear()


class SignalNoiseEffect(TransitionEffect):
    """Banda de interferencia horizontal que se desplaza hacia abajo."""

    def __init__(self, duration: float = 3.0, band_height: int = 3, speed_ms: int = 30) -> None:
        super().__init__()
        self.duration = duration
        self.band_height = band_height
        self.speed = speed_ms / 1000

    async def run(self, width: int, height: int) -> None:
        colors = [Style(color=palette.HOT_DIM), Style(color=palette.ELECTRIC_DIM), Style(color=palette.STEEL_DIM)]
        band_start = random.randrange(max(1, height - self.band_height + 1))
        end = _deadline(self.duration)
        while _now() < end:
            grid = blank_grid(width, height)
            style = random.choice(colors)
            for row in range(band_start, min(band_start + self.band_height, height)):
                for col in range(width):
                    r = random.random()
                    if r < 0.2:
                        ch = random.choice(palette.FRAME_CHARS)
                    elif r < 0.4:
                        ch = "░"
                    elif r < 0.6:
                        ch = "▒"
                    else:
                        ch = " "
                    grid[row][col] = (ch, style)
            self.set_frame(grid_to_strips(grid))
            await asyncio.sleep(self.speed)
            self.clear()
            band_start = (band_start + 1) % max(1, height)
            await asyncio.sleep(self.speed)


class DatamoshEffect(TransitionEffect):
    """Bloques rectangulares de basura que aparecen y desaparecen — códec roto."""

    def __init__(self, duration: float = 3.0, intensity: int = 3) -> None:
        super().__init__()
        self.duration = duration
        self.intensity = max(1, intensity)

    async def run(self, width: int, height: int) -> None:
        colors = [Style(color=palette.ACCENT), Style(color=palette.HOT), Style(color=palette.ELECTRIC)]
        end = _deadline(self.duration)
        while _now() < end:
            grid = blank_grid(width, height)
            for b in range(self.intensity):
                bw = random.randint(5, 19)
                bh = random.randint(1, 3)
                dst_row = random.randrange(max(1, height - bh + 1))
                dst_col = random.randrange(max(1, width - bw + 1))
                style = colors[b % len(colors)]
                for r in range(bh):
                    row = dst_row + r
                    if row >= height:
                        continue
                    for c in range(bw):
                        col = dst_col + c
                        if col >= width:
                            continue
                        roll = random.random()
                        ch = random.choice(palette.FRAME_CHARS) if roll < 0.33 else ("▓" if roll < 0.66 else "░")
                        grid[row][col] = (ch, style)
            self.set_frame(grid_to_strips(grid))
            await asyncio.sleep(0.06 / self.intensity + 0.02)
            self.clear()
            await asyncio.sleep(0.03 / self.intensity + 0.01)


# ── manifest_atmosphere.sh ────────────────────────────────────


class VignetteEffect(TransitionEffect):
    """Bordes/esquinas oscurecidos — foco claustrofóbico al centro."""

    def __init__(self, duration: float = 4.0, intensity: int = 3) -> None:
        super().__init__()
        self.duration = duration
        self.intensity = intensity

    async def run(self, width: int, height: int) -> None:
        style = Style(color=palette.ACCENT)
        chars = {1: "█", 2: "▓", 3: "▒", 4: "░"}
        end = _deadline(self.duration)
        while _now() < end:
            grid = blank_grid(width, height)
            for row in range(height):
                row_dist = min(row + 1, height - row)
                for col in range(width):
                    col_dist = min(col + 1, width - col)
                    dist = min(row_dist, col_dist)
                    if dist <= self.intensity:
                        grid[row][col] = (chars.get(dist, "░"), style)
            self.set_frame(grid_to_strips(grid))
            await asyncio.sleep(0.2 + random.uniform(0.8, 1.2))
            self.clear()
            await asyncio.sleep(0.6 + random.uniform(0, 0.3))


class AfterimageEffect(TransitionEffect):
    """Texto con ghosting tipo fósforo CRT — flash, apagón, fantasma, fade."""

    def __init__(self, text: str = "I am here", row: int | None = None) -> None:
        super().__init__()
        self.text = text
        self._row = row

    async def run(self, width: int, height: int) -> None:
        row = self._row if self._row is not None else height // 2
        col = max(0, (width - len(self.text)) // 2)

        def frame(chars: str, style: Style) -> None:
            grid = blank_grid(width, height)
            for i, ch in enumerate(chars):
                c = col + i
                if 0 <= c < width and ch != " ":
                    grid[row][c] = (ch, style)
            self.set_frame(grid_to_strips(grid))

        frame(self.text, Style(color=palette.STEEL, bold=True))
        await asyncio.sleep(1.0)
        self.clear()
        await asyncio.sleep(0.1)
        frame(self.text, Style(color=palette.ELECTRIC))
        await asyncio.sleep(0.6)
        frame(self.text, Style(color=palette.ELECTRIC_DIM))
        await asyncio.sleep(0.5)
        frame("".join(ch if random.random() > 1 / 3 else " " for ch in self.text), Style(color=palette.COOL_DIM))
        await asyncio.sleep(0.4)
        frame("".join(ch if random.random() > 0.5 else " " for ch in self.text), Style(color=palette.DIM))
        await asyncio.sleep(0.4)
        frame("".join(ch if random.random() < 0.2 else " " for ch in self.text), Style(color=palette.DIM))
        await asyncio.sleep(0.3)
        self.clear()


# ── manifest_spatial.sh ────────────────────────────────────────

_RING_CHARS = "·░▒▓▒░·"
_RING_OFFSETS = {
    0: (2, 0), 1: (1.4, 0.7), 2: (0, 1), 3: (-1.4, 0.7),
    4: (-2, 0), 5: (-1.4, -0.7), 6: (0, -1), 7: (1.4, -0.7),
}


def _ring_point(cx: int, cy: int, r: int, angle_idx: int) -> tuple[int, int]:
    dx, dy = _RING_OFFSETS[angle_idx % 8]
    return cx + round(dx * r), cy + round(dy * r)


class RippleEffect(TransitionEffect):
    """Anillos concéntricos que se expanden desde el centro — sonar."""

    def __init__(self, count: int = 3, speed_ms: int = 40) -> None:
        super().__init__()
        self.count = count
        self.speed = speed_ms / 1000

    async def run(self, width: int, height: int) -> None:
        cx, cy = width // 2, height // 2
        max_radius = max(height, width // 2)
        for _wave in range(self.count):
            grid = blank_grid(width, height)
            for r in range(1, max_radius + 1):
                steps = max(8, r * 8)
                ch = _RING_CHARS[r % len(_RING_CHARS)]
                if r < 3:
                    style = Style(color=palette.COOL, bold=True)
                elif r < 6:
                    style = Style(color=palette.COOL)
                else:
                    style = Style(color=palette.COOL_DIM)
                for s in range(steps):
                    angle_idx = (s * 8) // steps
                    px, py = _ring_point(cx, cy, r, angle_idx)
                    if 0 <= px < width and 0 <= py < height:
                        grid[py][px] = (ch, style)

                inner = r - 3
                if inner >= 1:
                    isteps = max(8, inner * 8)
                    for s in range(isteps):
                        angle_idx = (s * 8) // isteps
                        px, py = _ring_point(cx, cy, inner, angle_idx)
                        if 0 <= px < width and 0 <= py < height:
                            grid[py][px] = (" ", None)

                self.set_frame(grid_to_strips(grid))
                await asyncio.sleep(self.speed)

            for r in range(max(1, max_radius - 2), max_radius + 1):
                isteps = max(8, r * 8)
                for s in range(isteps):
                    angle_idx = (s * 8) // isteps
                    px, py = _ring_point(cx, cy, r, angle_idx)
                    if 0 <= px < width and 0 <= py < height:
                        grid[py][px] = (" ", None)
            self.set_frame(grid_to_strips(grid))
            await asyncio.sleep(0.3)
            self.clear()
