#!/bin/sh
# Serve site/ locally with the same asset layout the Pages workflow publishes.
#
#   ./tools/preview_site.sh        -> http://localhost:8000/
set -eu
cd "$(dirname "$0")/.."
mkdir -p site/assets
cp assets/plumb-app-icon.png assets/plumb-demo.gif \
   assets/plumb-corpus.png assets/plumb-social.png site/assets/
echo "serving http://localhost:8000/  (Ctrl-C to stop)"
exec uv run python -m http.server 8000 --directory site
