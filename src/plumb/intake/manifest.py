"""Manifest scanning: what a checkout looks like (I3).

`scan_manifests(checkout)` records which dependency and entry-point manifests
exist at the checkout root — `uv.lock`, `pyproject.toml`, `requirements*.txt`,
`environment.yml`, `Makefile`, `main.py` — so C3 can later pick entry points.
Manifests are read at the root only: a nested `pyproject.toml` is a different
package and belongs to that project's own intake, not this checkout's.

The scan is pure reading of the checkout tree: no network, no subprocess, no
side effects. Absence is recorded as `None`/empty, never as a silent drop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from plumb.intake.checkout import Checkout

__all__ = ["ManifestScan", "scan_manifests"]


@dataclass(frozen=True)
class ManifestScan:
    """The manifests present at a checkout's root, as relative paths."""

    uv_lock: Path | None
    pyproject: Path | None
    requirements: tuple[Path, ...]
    environment_yml: Path | None
    makefile: Path | None
    main_py: Path | None


def scan_manifests(checkout: Checkout) -> ManifestScan:
    """Record which manifests exist at the checkout root."""
    root = checkout.checkout_dir
    requirements = tuple(sorted(root.glob("requirements*.txt")))

    def present(name: str) -> Path | None:
        path = root / name
        return Path(name) if path.is_file() else None

    return ManifestScan(
        uv_lock=present("uv.lock"),
        pyproject=present("pyproject.toml"),
        requirements=tuple(path.relative_to(root) for path in requirements),
        environment_yml=present("environment.yml"),
        makefile=present("Makefile"),
        main_py=present("main.py"),
    )