"""Entry-point resolution (R1).

`resolve_entrypoint(checkout, manifests, explicit=None)` decides *what runs*.
An explicit argv always wins and is recorded verbatim. Otherwise exactly two
discovery rules apply — a single `[project.scripts]` entry in `pyproject.toml`
runs as `uv run <name>`, and a root `main.py` runs as `python main.py` — and
the rule that fired is recorded as the entry point's `source`. More than one
candidate is `EntryPointAmbiguous`; none is `EntryPointMissing`. Plumb never
guesses between candidates: a guessed entry point is a wrong binding waiting
to happen, and a wrong binding must surface as `UNVERIFIED`, not as a verdict.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.intake.checkout import resolve_local
from plumb.intake.manifest import scan_manifests
from plumb.run.causes import EntryPointAmbiguous, EntryPointMissing
from plumb.run.entrypoint import EntryPoint, resolve_entrypoint


def make_checkout(root: Path, files: dict[str, bytes]):
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return resolve_local(root)


def resolve(checkout, explicit=None) -> EntryPoint:
    return resolve_entrypoint(checkout, scan_manifests(checkout), explicit=explicit)


ONE_SCRIPT = b'[project]\nname = "demo"\n\n[project.scripts]\nreproduce = "demo.cli:main"\n'
TWO_SCRIPTS = (
    b'[project]\nname = "demo"\n\n[project.scripts]\n'
    b'reproduce = "demo.cli:main"\nfigures = "demo.cli:figures"\n'
)


class TestExplicit:
    def test_an_explicit_argv_wins_and_is_recorded_verbatim(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"main.py": b"print(1)\n"})
        entry = resolve(checkout, explicit=["python", "scripts/run.py", "--seed", "0"])
        assert entry.argv == ("python", "scripts/run.py", "--seed", "0")
        assert entry.source == "explicit"

    def test_an_explicit_argv_wins_over_an_ambiguous_checkout(self, tmp_path: Path) -> None:
        checkout = make_checkout(
            tmp_path / "proj", {"main.py": b"print(1)\n", "pyproject.toml": ONE_SCRIPT}
        )
        entry = resolve(checkout, explicit=["make", "all"])
        assert entry.argv == ("make", "all")

    def test_an_empty_explicit_argv_is_missing_not_discovered(self, tmp_path: Path) -> None:
        # An empty override is a caller mistake; falling through to discovery
        # would silently run something the caller did not ask for.
        checkout = make_checkout(tmp_path / "proj", {"main.py": b"print(1)\n"})
        with pytest.raises(EntryPointMissing):
            resolve(checkout, explicit=[])


class TestDiscovery:
    def test_a_single_pyproject_script_runs_through_uv(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"pyproject.toml": ONE_SCRIPT})
        entry = resolve(checkout)
        assert entry.argv == ("uv", "run", "reproduce")
        assert entry.source == "pyproject-script"

    def test_a_root_main_py_runs_through_python(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"main.py": b"print(1)\n"})
        entry = resolve(checkout)
        assert entry.argv == ("python", "main.py")
        assert entry.source == "main.py"

    def test_a_pyproject_without_scripts_is_not_a_candidate(self, tmp_path: Path) -> None:
        checkout = make_checkout(
            tmp_path / "proj",
            {"pyproject.toml": b'[project]\nname = "demo"\n', "main.py": b"print(1)\n"},
        )
        assert resolve(checkout).source == "main.py"

    def test_a_nested_main_py_is_not_a_candidate(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"src/main.py": b"print(1)\n"})
        with pytest.raises(EntryPointMissing):
            resolve(checkout)


class TestNamedCauses:
    def test_a_script_and_a_main_py_are_ambiguous(self, tmp_path: Path) -> None:
        checkout = make_checkout(
            tmp_path / "proj", {"pyproject.toml": ONE_SCRIPT, "main.py": b"print(1)\n"}
        )
        with pytest.raises(EntryPointAmbiguous) as info:
            resolve(checkout)
        message = str(info.value)
        assert "uv run reproduce" in message and "python main.py" in message

    def test_two_pyproject_scripts_are_ambiguous(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"pyproject.toml": TWO_SCRIPTS})
        with pytest.raises(EntryPointAmbiguous):
            resolve(checkout)

    def test_nothing_runnable_is_missing(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"README.md": b"# demo\n"})
        with pytest.raises(EntryPointMissing):
            resolve(checkout)

    def test_an_unreadable_pyproject_is_missing_not_a_crash(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"pyproject.toml": b"[project\nbroken"})
        with pytest.raises(EntryPointMissing) as info:
            resolve(checkout)
        assert "pyproject.toml" in str(info.value)

    def test_each_cause_carries_its_unverified_name(self) -> None:
        assert EntryPointMissing.cause == "ENTRYPOINT_MISSING"
        assert EntryPointAmbiguous.cause == "ENTRYPOINT_AMBIGUOUS"
        assert issubclass(EntryPointMissing, RuntimeError)
        assert issubclass(EntryPointAmbiguous, RuntimeError)
