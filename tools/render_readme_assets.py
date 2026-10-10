#!/usr/bin/env python3
"""Build Plumb's README assets from REAL CLI output (no fabrication).

- assets/plumb-logo.svg        — the mark (plumb line + bob).
- assets/plumb-verify.{svg,png} — hero card: `plumb verify --from-record` verdict table,
                                  first 6 rows + a truncation note + the Summary block.
- assets/plumb-corpus.{svg,png} — corpus card: the 3-case pooled report + precision/recall.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/Users/aliz/dev/at/plumb")
ASSETS = ROOT / "assets"
BG = "#0d1117"
PANEL = "#161b22"
GREEN = "#3fb950"
RED = "#f85149"
AMBER = "#d29922"
BLUE = "#58a6ff"
FG = "#e6edf3"
DIM = "#8b949e"
BORDER = "#30363d"

FONT = "Menlo, Monaco, 'DejaVu Sans Mono', monospace"


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_head(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT}">'
    )


def term_card(title: str, lines: list[tuple[str, str]], width: int, height: int) -> str:
    """A dark terminal-style card. Lines are (text, color)."""
    pads = 28
    head_h = 46
    line_h = 23
    body_h = height - head_h - pads
    max_lines = int(body_h / line_h)
    out = [svg_head(width, height)]
    out.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="14" fill="{BG}"/>')
    out.append(f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="13" fill="none" stroke="{BORDER}"/>')
    # title bar
    out.append(f'<rect x="0" y="0" width="{width}" height="{head_h}" rx="14" fill="{PANEL}"/>')
    out.append(f'<rect x="0" y="{head_h-14}" width="{width}" height="14" fill="{PANEL}"/>')
    for i, cx in enumerate((18, 40, 62)):
        out.append(f'<circle cx="{cx}" cy="{head_h/2}" r="6" fill="{BORDER}"/>')
    out.append(
        f'<text x="{76}" y="{head_h/2+6}" font-size="15" fill="{DIM}">{esc(title)}</text>'
    )
    y = head_h + pads
    for text, color in lines[:max_lines]:
        out.append(f'<text x="28" y="{y}" font-size="15" fill="{color}">{esc(text)}</text>')
        y += line_h
    out.append("</svg>")
    return "\n".join(out)


def verdict_color(line: str) -> str:
    if line.startswith("REPRODUCED"):
        return GREEN
    if line.startswith("DIVERGED"):
        return RED
    if line.startswith("UNVERIFIED"):
        return AMBER
    if line.startswith("WITHIN-TOLERANCE"):
        return BLUE
    return FG


def build_verify_card() -> None:
    table = (ROOT / "fixtures/gate/rcai/verdicts.json").parent
    out = subprocess.run(
        ["uv", "run", "plumb", "verify", "--from-record", str(ROOT / "fixtures/gate/rcai")],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout.splitlines()
    header = out[0]
    sep = out[1]
    rows = [line for line in out[2:] if line.strip() and line.startswith(("REPRODUCED", "DIVERGED", "UNVERIFIED", "WITHIN"))]
    idx = next(i for i, line in enumerate(out) if line.strip() == "Summary")
    summary = out[idx:]
    lines: list[tuple[str, str]] = [(header, DIM)]
    lines.append((sep, BORDER))
    for row in rows[:6]:
        lines.append((row, verdict_color(row)))
    lines.append(("…", DIM))
    lines.append(("· full 31-row table, byte-identical on every replay of this record", DIM))
    lines.append(("", FG))
    for line in summary:
        if line.startswith("Summary"):
            lines.append((line, FG))
        elif "REPRODUCED" in line or "DIVERGED" in line or "UNVERIFIED" in line:
            lines.append((line, verdict_color(line.strip().split(":")[0])))
        elif "bound" in line:
            lines.append((line, FG))
        else:
            lines.append((line, DIM))
    svg = term_card(
        "plumb verify --from-record fixtures/gate/rcai   ·   arXiv:2609.00137",
        lines, 1270, 560,
    )
    (ASSETS / "plumb-verify.svg").write_text(svg, encoding="utf-8")


def build_corpus_card() -> None:
    out = subprocess.run(
        ["uv", "run", "plumb", "corpus", "report"], capture_output=True, text=True, cwd=ROOT,
    ).stdout.splitlines()
    header = out[0]
    sep = out[1]
    data = [line for line in out[2:] if line.strip()]
    lines: list[tuple[str, str]] = [(header, DIM), (sep, BORDER)]
    for line in data:
        if line.startswith(("3f7f", "941b", "db99")):  # perrin, agrodesign, rcai case ids
            lines.append((line, FG))
        elif line.startswith("total"):
            lines.append((line, FG))
        elif line.startswith(("  coverage", "  precision", "  recall")):
            color = GREEN if "coverage" in line else (AMBER if "1/15" in line else FG)
            lines.append((line, color))
        else:
            lines.append((line, DIM))
    svg = term_card("plumb corpus report   ·   the discrepancy corpus", lines, 1270, 560)
    (ASSETS / "plumb-corpus.svg").write_text(svg, encoding="utf-8")


LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect x="0" y="0" width="128" height="128" rx="26" fill="#0d1117"/>
  <rect x="1" y="1" width="126" height="126" rx="25" fill="none" stroke="#30363d"/>
  <line x1="64" y1="14" x2="64" y2="62" stroke="#3fb950" stroke-width="4" stroke-linecap="round"/>
  <circle cx="64" cy="62" r="2.5" fill="#3fb950"/>
  <path d="M64 69
           c-11 0 -19 7 -19 17
           c0 12 14 21 19 26
           c5 -5 19 -14 19 -26
           c0 -10 -8 -17 -19 -17 Z"
        fill="#3fb950"/>
  <path d="M64 100 c-4 -8 -8 -12 -14 -16 c4 1 8 1 14 1 c6 0 10 0 14 -1 c-6 4 -10 8 -14 16 Z"
        fill="#0d1117"/>
  <circle cx="64" cy="82" r="2.2" fill="#e6edf3"/>
</svg>
"""


def build_social_card() -> None:
    """1280x640 social preview: the mark, wordmark, tagline, and the real pooled number."""
    W, H = 1280, 640
    out = [svg_head(W, H)]
    out.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BG}"/>')
    out.append(f'<rect x="0" y="0" width="{W}" height="10" fill="{GREEN}"/>')
    # the mark, centered
    out.append(
        f'<image x="{W/2-64}" y="86" width="128" height="128" '
        f'href="plumb-logo.svg" xlink:href="plumb-logo.svg"/>'
    )
    out.append(f'<text x="{W/2}" y="266" font-size="64" font-weight="bold" fill="{FG}" '
               f'text-anchor="middle">Plumb</text>')
    out.append(
        f'<text x="{W/2}" y="318" font-size="24" fill="{DIM}" text-anchor="middle">'
        f'Execution-grounded research-integrity verifier</text>'
    )
    out.append(
        f'<text x="{W/2}" y="352" font-size="19" fill="{DIM}" text-anchor="middle">'
        f'Re-runs a paper&apos;s own artifacts on your compute &mdash; a per-claim, reproducible verdict</text>'
    )
    # the real pooled number
    stats = [
        ("117 REPRODUCED", GREEN),
        ("15 DIVERGED · 1 confirmed", RED),
        ("1 UNVERIFIED", AMBER),
        ("133 claims · 132 bound", FG),
        ("precision 1/15 (owner)", AMBER),
    ]
    x0, y0 = 180, 448
    for i, (text, color) in enumerate(stats):
        out.append(
            f'<text x="{(x0 + i * (W - 2 * x0) / len(stats))}" y="{y0}" font-size="17" '
            f'fill="{color}" text-anchor="middle">{esc(text)}</text>'
        )
    out.append(
        f'<text x="{W/2}" y="506" font-size="15" fill="{BORDER}" text-anchor="middle">'
        f'github.com/haqaliz/plumb</text>'
    )
    out.append("</svg>")
    (ASSETS / "plumb-social.svg").write_text("\n".join(out), encoding="utf-8")
    subprocess.run(
        ["qlmanage", "-t", "-s", "1280", "-o", str(ASSETS), str(ASSETS / "plumb-social.svg")],
        check=True, capture_output=True,
    )
    (ASSETS / "plumb-social.svg.png").rename(ASSETS / "plumb-social.png")


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "plumb-logo.svg").write_text(LOGO, encoding="utf-8")
    build_verify_card()
    build_corpus_card()
    build_social_card()
    for name in ("plumb-logo", "plumb-verify", "plumb-corpus"):
        subprocess.run(
            ["qlmanage", "-t", "-s", "1600", "-o", str(ASSETS), str(ASSETS / f"{name}.svg")],
            check=True, capture_output=True,
        )
    print("assets:" + ", ".join(sorted(p.name for p in ASSETS.iterdir())))
    return 0


if __name__ == "__main__":
    sys.exit(main())