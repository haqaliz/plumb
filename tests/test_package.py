"""The package skeleton exists and is importable.

This is the first failing test of the repo (M10, `CLAUDE.md` #7): it must fail with
`ModuleNotFoundError` before `pyproject.toml` or `src/plumb/` exist.
"""


def test_extract_package_imports() -> None:
    import plumb.extract

    assert plumb.extract is not None
