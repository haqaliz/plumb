"""The RunTrace record (R4): what actually happened, deterministically.

`build_trace(checkout, result, capture)` folds a run and its capture into a
`RunTrace`, and `serialize_trace` renders it as one canonical JSON line — the
record C6 will bundle and replay compares.

Pinned here:

- **run_id** is SHA-256 over ``argv + tree hash + sorted locatable artifact
  hashes``: two runs of the same program on the same checkout get the same id
  even though their run dirs and mtimes differ, and stderr (diagnostic-only)
  cannot move it.
- **Byte identity across processes** under varying ``PYTHONHASHSEED``, so no
  dict or set ordering reaches the bytes.
- **No absolute run-side paths** in the record: the run dir, working copy and
  checkout location never appear; outputs are relpaths plus hashes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from plumb.intake.checkout import resolve_local
from plumb.intake.env import EnvBuild
from plumb.intake.tree import TreeHash
from plumb.run.capture import Artifact, StaleOutput, capture_outputs
from plumb.run.causes import NO_ARTIFACT, STALE_ARTIFACT, WONT_RUN
from plumb.run.entrypoint import EntryPoint
from plumb.run.runner import RunFailure, run_entrypoint
from plumb.run.trace import RunTrace, build_trace, derive_run_id, serialize_trace

_THIS_DIR = Path(__file__).parent
_SRC = _THIS_DIR.parents[1] / "src"

SEEDS = ("0", "1", "12345", "random")

OK_BUILD = EnvBuild(ok=True, policy="lockfile", detail="stub")
DETERMINISTIC = "import json; json.dump({'auc': 0.91}, open('out.json', 'w')); print('AUC = 0.91')"

_CHILD_PROGRAM = """\
import sys

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])

from test_trace import child_main

child_main()
"""


def sample_trace() -> RunTrace:
    """A fixed trace with non-ASCII, a failure, stale outputs and several artifacts."""
    artifacts = (
        Artifact("csv", "sub/data.csv", "c" * 64, 21, 1_700_000_000_000_000_001),
        Artifact("json", "out.json", "a" * 64, 13, 1_700_000_000_000_000_000),
        Artifact("stderr", "<stderr>", "e" * 64, 4, None, diagnostic_only=True),
        Artifact("stdout", "<stdout>", "b" * 64, 11, None),
    )
    tree = TreeHash(scheme="plumb", digest="d" * 64)
    argv = ("python", "main.py", "--cohort", "µ-cohort")
    return RunTrace(
        run_id=derive_run_id(argv, tree, artifacts),
        tree_hash=tree,
        argv=argv,
        entrypoint_source="main.py",
        cwd=".",
        env_policy="lockfile",
        timeout_seconds=1800,
        started_at_ns=1_700_000_000_000_000_000,
        exit_code=3,
        failure=RunFailure(WONT_RUN, "exited with code 3"),
        artifacts=artifacts,
        stale=(StaleOutput("results/old.json", 1_000_000_000_000_000_000, 9),),
        causes=(),
    )


def child_main() -> None:
    sys.stdout.buffer.write(serialize_trace(sample_trace()))


def make_checkout(root: Path, files: dict[str, bytes] | None = None):
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in (files or {"README.md": b"# demo\n"}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    return resolve_local(root)


def traced(checkout, program: str, run_dir: Path) -> RunTrace:
    entry = EntryPoint(argv=(sys.executable, "-c", program), source="explicit")
    result = run_entrypoint(checkout, OK_BUILD, entry, run_dir=run_dir)
    return build_trace(checkout, result, capture_outputs(result))


class TestBuildTrace:
    def test_the_trace_records_what_ran(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj")
        trace = traced(checkout, DETERMINISTIC, tmp_path / "run")
        assert trace.argv == (sys.executable, "-c", DETERMINISTIC)
        assert trace.entrypoint_source == "explicit"
        assert trace.cwd == "."
        assert trace.env_policy == "lockfile"
        assert trace.tree_hash == checkout.tree_hash
        assert trace.exit_code == 0
        assert trace.failure is None
        assert {a.relpath for a in trace.artifacts} == {"<stderr>", "<stdout>", "out.json"}
        assert trace.causes == ()

    def test_failures_stale_outputs_and_causes_are_carried(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"old.json": b"{}"})
        os.utime(checkout.checkout_dir / "old.json", (1_000_000_000, 1_000_000_000))
        trace = traced(checkout, "pass", tmp_path / "run")
        assert trace.causes == (NO_ARTIFACT,)
        assert [s.relpath for s in trace.stale] == ["old.json"]

        failed = traced(checkout, "import sys; sys.exit(2)", tmp_path / "run2")
        assert failed.failure == RunFailure(WONT_RUN, "exited with code 2")
        assert failed.exit_code == 2


class TestRunId:
    def test_the_same_program_on_the_same_checkout_gets_the_same_id(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj")
        first = traced(checkout, DETERMINISTIC, tmp_path / "run1")
        second = traced(checkout, DETERMINISTIC, tmp_path / "run2")
        assert first.started_at_ns != second.started_at_ns
        assert first.run_id == second.run_id

    def test_a_different_output_or_argv_changes_the_id(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj")
        base = traced(checkout, DETERMINISTIC, tmp_path / "run1")
        other_output = traced(checkout, DETERMINISTIC.replace("0.91", "0.92"), tmp_path / "run2")
        assert base.run_id != other_output.run_id
        artifacts = base.artifacts
        assert derive_run_id(("python", "other.py"), base.tree_hash, artifacts) != base.run_id

    def test_stderr_does_not_move_the_id(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj")
        quiet = traced(checkout, DETERMINISTIC, tmp_path / "run1")
        base = derive_run_id(quiet.argv, quiet.tree_hash, quiet.artifacts)
        noisy = tuple(
            Artifact(a.kind, a.relpath, "f" * 64, 99, None, True) if a.diagnostic_only else a
            for a in quiet.artifacts
        )
        assert derive_run_id(quiet.argv, quiet.tree_hash, noisy) == base

    def test_the_input_order_is_pinned(self) -> None:
        trace = sample_trace()
        reversed_artifacts = tuple(reversed(trace.artifacts))
        assert derive_run_id(trace.argv, trace.tree_hash, reversed_artifacts) == trace.run_id


class TestSerialization:
    def test_the_record_is_one_canonical_json_line(self) -> None:
        data = serialize_trace(sample_trace())
        assert data.endswith(b"\n") and data.count(b"\n") == 1
        document = json.loads(data)
        assert list(document) == sorted(document)
        assert document["failure"] == {"cause": WONT_RUN, "detail": "exited with code 3"}
        assert document["stale"] == [
            {"cause": STALE_ARTIFACT, "mtime_ns": 1_000_000_000_000_000_000,
             "relpath": "results/old.json", "size": 9}
        ]
        assert "µ-cohort" in data.decode("utf-8")

    def test_byte_identical_across_processes(self) -> None:
        outputs = {}
        for seed in SEEDS:
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
            result = subprocess.run(
                [sys.executable, "-c", _CHILD_PROGRAM, str(_THIS_DIR), str(_SRC)],
                env=env, capture_output=True, timeout=120, check=False,
            )
            assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
            outputs[seed] = result.stdout
        assert len(set(outputs.values())) == 1, outputs
        assert outputs["0"] == serialize_trace(sample_trace())

    def test_no_run_side_absolute_paths_are_recorded(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"old.json": b"{}"})
        os.utime(checkout.checkout_dir / "old.json", (1_000_000_000, 1_000_000_000))
        entry = EntryPoint(argv=("python3", "-c", DETERMINISTIC), source="explicit")
        result = run_entrypoint(checkout, OK_BUILD, entry, run_dir=tmp_path / "run")
        text = serialize_trace(build_trace(checkout, result, capture_outputs(result))).decode()
        for path in (tmp_path, tmp_path.resolve(), result.run_dir, result.workdir):
            assert str(path) not in text
