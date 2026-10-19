#!/bin/sh
# Build the README/landing-page demo GIF from a real replay.
#
# Dev-time only: needs rsvg-convert and ImageMagick. The replay itself is
# offline and deterministic; the GIF is rendered from its actual output, so it
# is reproducible rather than a screencast.
set -eu
cd "$(dirname "$0")/.."
exec uv run python tools/render_demo_gif.py
