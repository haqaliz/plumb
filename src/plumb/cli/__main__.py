"""`python -m plumb.cli`: run the CLI as a module (same entry as the console script)."""

from __future__ import annotations

import sys

from plumb.cli import main

if __name__ == "__main__":
    sys.exit(main())