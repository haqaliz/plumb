"""Entry-point resolution: what runs (R1).

`resolve_entrypoint(checkout, manifests, explicit=None)` returns the exact argv
the runner will execute, and records which rule chose it:

- **``explicit``** — the caller's argv, verbatim. It always wins.
- **``pyproject-script``** — exactly one `[project.scripts]` entry in the root
  `pyproject.toml`, run as ``uv run <name>``.
- **``main.py``** — a root `main.py`, run as ``python main.py``.

Those are the only two discovery rules. More than one candidate is
`EntryPointAmbiguous` and none is `EntryPointMissing`: Plumb never picks
between candidates, because a guessed entry point is a wrong binding, and a
wrong binding must end as `UNVERIFIED` rather than as a verdict on the wrong
run. An unreadable `pyproject.toml` could be hiding a script, so it too is
`EntryPointMissing` rather than a silent fall-through to `main.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import tomllib

from plumb.intake.checkout import Checkout
from plumb.intake.manifest import ManifestScan
from plumb.run.causes import EntryPointAmbiguous, EntryPointMissing

__all__ = ["EntryPoint", "resolve_entrypoint"]


@dataclass(frozen=True)
class EntryPoint:
    """The exact argv to run, and the rule that chose it."""

    argv: tuple[str, ...]
    source: str  # "explicit" | "pyproject-script" | "main.py"


def resolve_entrypoint(
    checkout: Checkout,
    manifests: ManifestScan,
    explicit: Sequence[str] | None = None,
) -> EntryPoint:
    """Explicit wins; else exactly one discovered candidate; else a named cause."""
    if explicit is not None:
        argv = tuple(explicit)
        if not argv:
            raise EntryPointMissing("explicit entry point is empty")
        return EntryPoint(argv=argv, source="explicit")

    candidates: list[EntryPoint] = []
    if manifests.pyproject is not None:
        for name in _pyproject_scripts(checkout, manifests):
            candidates.append(
                EntryPoint(argv=("uv", "run", name), source="pyproject-script")
            )
    if manifests.main_py is not None:
        candidates.append(EntryPoint(argv=("python", "main.py"), source="main.py"))

    if not candidates:
        raise EntryPointMissing(
            f"no entry point in {checkout.checkout_dir}: no [project.scripts] "
            "entry and no root main.py; pass one explicitly"
        )
    if len(candidates) > 1:
        found = "; ".join(" ".join(c.argv) for c in candidates)
        raise EntryPointAmbiguous(
            f"{len(candidates)} entry points discovered ({found}); pass one explicitly"
        )
    return candidates[0]


def _pyproject_scripts(checkout: Checkout, manifests: ManifestScan) -> list[str]:
    """The `[project.scripts]` names, sorted; an unreadable file is a named cause."""
    path = checkout.checkout_dir / manifests.pyproject
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise EntryPointMissing(
            f"pyproject.toml is unreadable ({exc}); it may declare an entry "
            "point, so none is guessed — pass one explicitly"
        ) from exc
    scripts = data.get("project", {}).get("scripts", {})
    return sorted(scripts) if isinstance(scripts, dict) else []
