"""The package skeleton exists and is importable, and its release metadata is coherent.

The first test is the repo's first failing test (M10, `CLAUDE.md` #7): it must fail with
`ModuleNotFoundError` before `pyproject.toml` or `src/plumb/` exist. The metadata tests pin
the packaging contract a published distribution depends on — one version, one console script,
no drift between `plumb.__version__` and what `pyproject.toml` declares.
"""

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_extract_package_imports() -> None:
    import plumb.extract

    assert plumb.extract is not None


def test_the_package_declares_a_pep440_version() -> None:
    import plumb

    assert isinstance(plumb.__version__, str)
    parts = plumb.__version__.split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts), plumb.__version__


def test_the_imported_version_matches_the_distribution_metadata() -> None:
    """A published wheel must not disagree with `plumb.__version__`."""
    import plumb

    project = _pyproject()["project"]
    assert plumb.__version__ == project["version"]


def test_the_distribution_name_is_not_shadowed_by_an_unrelated_package() -> None:
    """`plumb` on PyPI is an unrelated 2018 library, so the dist name must differ."""
    name = _pyproject()["project"]["name"]
    assert name != "plumb"
    assert name.startswith("plumb")


def test_the_console_script_points_at_an_importable_main() -> None:
    from plumb.cli import main

    scripts = _pyproject()["project"]["scripts"]
    target = scripts["plumb"]
    module, _, attribute = target.partition(":")
    assert module == "plumb.cli"
    assert attribute == "main"
    assert callable(main)
