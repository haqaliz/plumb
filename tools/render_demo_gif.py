#!/usr/bin/env python3
"""Build `assets/plumb-demo.gif` from REAL CLI output (no fabricated frames).

The committed-record replay is byte-identical on every run, so the animation is
deterministic too: a dark terminal card fills in as the demo runs -- the version,
the command, the verdict rows, the summary. Frames are SVG -> PNG with
`rsvg-convert` (the same rasterizer as `tools/render_readme_assets.py`) and
stitched with ImageMagick.

Dev-time only, like the other asset scripts: it shells out to the CLI, the
rasterizer and ImageMagick. Nothing here runs in tests or CI.

    ./tools/record_demo.sh          # -> assets/plumb-demo.gif
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
sys.path.insert(0, str(Path(__file__).parent))

from render_readme_assets import (  # noqa: E402
    AMBER, BORDER, DIM, FG, GREEN, term_card, verdict_color,
)

W, H = 1400, 620
TITLE = "plumb — the 60-second demo (a real replay, byte-identical every time)"
PROMPT_VERSION = "$ uv run plumb --version"
PROMPT_REPLAY = "$ uv run plumb verify --from-record fixtures/gate/rcai"


def _cli(*argv: str) -> list[str]:
    # `verify` exits 1 when any claim is UNVERIFIED (here: the one NO_BINDING), by
    # design -- the exit code is the verdict contract, not a failure to render.
    result = subprocess.run(
        ["uv", "run", "plumb", *argv], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode not in (0, 1) or not result.stdout:
        raise SystemExit(f"plumb {' '.join(argv)} failed:\n{result.stderr}")
    return result.stdout.splitlines()


def _frames() -> list[list[tuple[str, str]]]:
    version = _cli("--version")[0]
    out = _cli("verify", "--from-record", "fixtures/gate/rcai")
    header, separator = out[0], out[1]
    rows = [line for line in out[2:] if line.startswith(
        ("REPRODUCED", "DIVERGED", "UNVERIFIED", "WITHIN"))]
    summary_at = next(i for i, line in enumerate(out) if line.strip() == "Summary")
    summary = out[summary_at:]

    head = [(PROMPT_VERSION, GREEN), (version, FG), ("", FG), (PROMPT_REPLAY, GREEN)]
    table_top = head + [(header, DIM), (separator, BORDER)]
    tinted = [(row, verdict_color(row)) for row in rows]

    def summary_lines() -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = []
        for line in summary:
            if line.startswith("Summary") or "bound" in line:
                lines.append((line, FG))
            elif ":" in line and line.strip().split(":")[0] in (
                    "REPRODUCED", "DIVERGED", "UNVERIFIED", "WITHIN-TOLERANCE"):
                lines.append((line, verdict_color(line.strip().split(":")[0])))
            else:
                lines.append((line, DIM))
        return lines

    return [
        head[:2],
        head,
        table_top + tinted[:4],
        table_top + tinted[:10] + [("…  (31 claims; the full table is in the record)", DIM)],
        table_top + tinted[:10] + [("…", DIM), ("", FG)] + summary_lines(),
    ]


def main() -> int:
    for tool in ("rsvg-convert", "magick"):
        if shutil.which(tool) is None:
            print(f"{tool} is required (brew install librsvg imagemagick)", file=sys.stderr)
            return 1

    ASSETS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pngs = []
        for index, lines in enumerate(_frames()):
            svg = Path(tmp) / f"frame{index}.svg"
            png = Path(tmp) / f"frame{index}.png"
            svg.write_text(term_card(TITLE, lines, W, H), encoding="utf-8")
            subprocess.run(
                ["rsvg-convert", "-w", str(W), "-o", str(png), str(svg)],
                check=True, capture_output=True,
            )
            # rsvg-convert leaves transparency outside the rounded card; GIF's
            # palette + optimization turns that into a white frame. Flatten onto
            # the card's own background before the sequence is encoded.
            subprocess.run(
                ["magick", str(png), "-background", "#0d1117", "-alpha", "remove",
                 "-alpha", "off", str(png)],
                check=True, capture_output=True,
            )
            pngs.append(png)

        # ImageMagick `-delay` is in 1/100 s, not milliseconds.
        delays = [110, 110, 120, 160, 320]
        argv = ["magick"]
        for png, delay in zip(pngs, delays):
            argv += ["-delay", str(delay), str(png)]
        argv += ["-loop", "0", "-layers", "Optimize", str(ASSETS / "plumb-demo.gif")]
        subprocess.run(argv, check=True, capture_output=True)

    size = (ASSETS / "plumb-demo.gif").stat().st_size
    print(f"assets/plumb-demo.gif  {size / 1024:.0f} KiB  {W}x{H}")
    return 0 if size < 10 * 1024 * 1024 else 1


if __name__ == "__main__":
    sys.exit(main())
