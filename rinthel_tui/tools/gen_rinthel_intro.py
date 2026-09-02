#!/usr/bin/env python3
"""Generate rinthel_tui/branding/rinthel-intro.txt.

Renders "RINTHEL" with pyfiglet (ansi_shadow font) and wraps it in a
noise -> left-to-right reveal -> stable flicker -> right-to-left fade
sequence, in the "--- Frame N ---" format that IntroAnimation (and, before
the migration, clifx's play_frames()) expects. Re-run this after changing
text/timing/noise density.
"""

import os
import random

import pyfiglet

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "branding", "rinthel-intro.txt")

TEXT = "RINTHEL"
FONT = "ansi_shadow"

NOISE_CHARS = ["░", "▒", "▓", "█", "╳"]

NOISE_FRAMES = 4
REVEAL_FRAMES = 9
STABLE_FRAMES = 4
FADE_FRAMES = 3

random.seed(1337)


def render_clean_grid():
    art = pyfiglet.Figlet(font=FONT).renderText(TEXT)
    lines = art.rstrip("\n").split("\n")
    # Drop trailing all-blank lines pyfiglet sometimes appends.
    while lines and not lines[-1].strip():
        lines.pop()
    width = max(len(l) for l in lines)
    lines = [l.ljust(width) for l in lines]
    return lines, width, len(lines)


def noise_char():
    return random.choice(NOISE_CHARS)


def noise_row(width, density=0.9):
    return "".join(noise_char() if random.random() < density else " " for _ in range(width))


def frame_noise(width, height):
    return "\n".join(noise_row(width) for _ in range(height))


def frame_reveal(clean, width, height, step, total_steps):
    """step is 1-indexed within [1, total_steps]; reveal grows left->right."""
    threshold = width * step / total_steps
    edge_band = max(2, width // 12)  # extra-glitchy band right at the wipe edge
    out_lines = []
    for row in clean:
        chars = []
        for x, ch in enumerate(row):
            if x < threshold - edge_band:
                chars.append(ch)
            elif x < threshold:
                # near the wipe edge: mostly noise, some clean bleeding through
                chars.append(ch if random.random() < 0.25 else noise_char())
            else:
                chars.append(noise_char() if random.random() < 0.55 else " ")
        out_lines.append("".join(chars))
    return "\n".join(out_lines)


def frame_stable(clean, glitch_count):
    height = len(clean)
    width = len(clean[0]) if clean else 0
    grid = [list(row) for row in clean]
    ink_cells = [(y, x) for y in range(height) for x in range(width) if grid[y][x] != " "]
    for (y, x) in random.sample(ink_cells, min(glitch_count, len(ink_cells))):
        grid[y][x] = noise_char()
    return "\n".join("".join(row) for row in grid)


def frame_fade(clean, width, height, step, total_steps):
    """step is 1-indexed within [1, total_steps]; wipe clears right->left."""
    if step >= total_steps:
        return "\n".join(" " * width for _ in range(height))
    blank_frac = step / total_steps
    corrupt_frac = min(1.0, blank_frac + 0.15)
    out_lines = []
    for row in clean:
        chars = []
        for x, ch in enumerate(row):
            r = (width - 1 - x) / max(1, width - 1)  # 0 at right edge, 1 at left edge
            if r < blank_frac:
                chars.append(" ")
            elif r < corrupt_frac:
                chars.append(noise_char() if random.random() < 0.7 else " ")
            else:
                chars.append(ch)
        out_lines.append("".join(chars))
    return "\n".join(out_lines)


def build_frames():
    clean, width, height = render_clean_grid()
    frames = []

    for _ in range(NOISE_FRAMES):
        frames.append(frame_noise(width, height))

    for i in range(1, REVEAL_FRAMES + 1):
        frames.append(frame_reveal(clean, width, height, i, REVEAL_FRAMES))

    clean_joined = "\n".join(clean)
    frames.append(clean_joined)  # one fully clean frame before the flicker starts
    for _ in range(STABLE_FRAMES - 1):
        frames.append(frame_stable(clean, glitch_count=2))

    for i in range(1, FADE_FRAMES + 1):
        frames.append(frame_fade(clean, width, height, i, FADE_FRAMES))

    return frames


def main():
    frames = build_frames()
    with open(OUT_PATH, "w") as f:
        for idx, frame in enumerate(frames, 1):
            f.write(f"--- Frame {idx} ---\n")
            f.write(frame)
            if not frame.endswith("\n"):
                f.write("\n")
    print(f"wrote {len(frames)} frames to {os.path.abspath(OUT_PATH)}")


if __name__ == "__main__":
    main()
