#!/usr/bin/env python3
"""Build the rounded-square app icon from the source mark (dev-time).

    assets/plumb-mark-source.jpg   the mark as found (black bars on cream)
    assets/plumb-app-icon.png      512x512, rounded corners, crisp bars
    assets/plumb-app-icon-240.png  240x240 for README/thumbnail use

The treatment is the one Vocca uses: the artwork on a rounded square, mark
centred with generous breathing room. The bars are re-thresholded from the
JPEG so the icon is crisp at small sizes rather than inheriting compression
softness. Deterministic: same source -> same bytes.

Requires ImageMagick (`magick`) and a temporary directory, nothing else.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "plumb-mark-source.jpg"

SIZE = 512
RADIUS = 112
BG = "#EBE8E3"   # sampled from the mark's own background
INK = "#1A1A1A"  # sampled from the mark
MARK_BOX = 400   # the mark's longest side, in the 512 tile


def _run(*argv: str) -> None:
    subprocess.run(list(argv), check=True, capture_output=True)


def _size(path: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        ["magick", "identify", "-format", "%w %h", str(path)], text=True
    )
    width, height = out.split()
    return int(width), int(height)


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing source mark: {SOURCE}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        mask = tmp / "mask.png"
        bars = tmp / "bars.png"
        square = tmp / "square.png"
        rounded = tmp / "rounded.png"

        # 1. crop to the mark, keep aspect, threshold to a hard black/white mask
        _run(
            "magick", str(SOURCE), "-fuzz", "12%", "-trim", "+repage",
            "-resize", f"{MARK_BOX}x{MARK_BOX}",
            "-colorspace", "gray", "-threshold", "50%", "-negate", str(mask),
        )
        width, height = _size(mask)

        # 2. paint the bars in ink, with the mask as the alpha channel
        _run(
            "magick", "-size", f"{width}x{height}", f"xc:{INK}",
            "(", str(mask), "-alpha", "off", ")",
            "-compose", "CopyOpacity", "-composite", str(bars),
        )

        # 3. centre on the cream tile
        _run(
            "magick", "-size", f"{SIZE}x{SIZE}", f"xc:{BG}",
            str(bars), "-gravity", "center", "-composite", str(square),
        )

        # 4. rounded corners
        _run(
            "magick", "-size", f"{SIZE}x{SIZE}", "xc:none", "-fill", "white",
            "-draw", f"roundrectangle 0,0,{SIZE - 1},{SIZE - 1},{RADIUS},{RADIUS}",
            str(rounded),
        )
        _run(
            "magick", str(square), str(rounded), "-alpha", "off",
            "-compose", "CopyOpacity", "-composite", str(ASSETS / "plumb-app-icon.png"),
        )

    _run(
        "magick", str(ASSETS / "plumb-app-icon.png"),
        "-resize", "240x240", str(ASSETS / "plumb-app-icon-240.png"),
    )
    print("assets/plumb-app-icon.png 512x512")
    print("assets/plumb-app-icon-240.png 240x240")
    return 0


if __name__ == "__main__":
    sys.exit(main())
