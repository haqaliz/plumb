"""Cross-process/seed determinism of the `--bank` path (cross-paper-coverage, Phase 4).

The milestone-1 number for the banked path: `plumb verify --bank --json` renders a
verdicts document that is byte-identical across fresh interpreters under different
`PYTHONHASHSEED` values. Single-process tests cannot make this claim — inside one
interpreter dict/set iteration order is stable, so the bytes only diverge once a
second process, with a different seed, builds the same document. So, exactly as
`tests/extract/test_determinism.py` does, the load-bearing tests here spawn fresh
interpreters with the seed passed through `env`, and compare their raw stdout
**bytes**.

What is *not* byte-identical across two runs is the last line. Each run banks its
own case: the case id is content-addressed over the record's bytes, and the trace
carries wall-clock provenance (`started_at_ns`, artifact `mtime_ns`), so two
different live runs of the same inputs bank two **distinct** cases. The
determinism contract is the render — the verdicts document — and the honesty rule
is to assert that the two runs each banked their own case, never that there is
"one banked case". The two cases are byte-identical in every member except
`trace.json`, and `trace.json` differs only in the two provenance fields.

1. The seed control: the children observably disagree about `hash()` under the
   seeds this file uses, so the byte-identity below is evidence about the renderer
   rather than evidence that the seed plumbing does nothing.
2. Two live `--bank --json` runs in fresh interpreters under different seeds:
   exit 0, the verdicts document byte-identical, each run's `banked <case_id>`
   line names a distinct 64-hex case id, and both cases exist under the redirected
   default store — byte-identical members except the two trace provenance fields.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[1]
_SRC = _REPO_ROOT / "src"

PAPER = _THIS_DIR / "fixtures" / "paper.md"
REPO = _THIS_DIR / "fixtures" / "repo"
BINDINGS = _THIS_DIR / "fixtures" / "bindings.json"

#: Two fixed seeds: `0` disables hash randomization, `1` and `12345` enable it
#: with fixed seeds — the same triple `tests/extract/test_determinism.py` uses.
FIXED_SEEDS = ("0", "1", "12345")

#: The one wall-clock field set the two runs' traces may differ in.
_PROVENANCE_FIELDS = ("started_at_ns", "mtime_ns")

_HEX64 = re.compile(r"[0-9a-f]{64}")


def child_main(payload: str, work_root: str, cwd: str) -> None:
    """Entry point for the spawned interpreter: raw bytes to stdout, nothing else.

    `probe` is the control payload: it reports what this interpreter's `hash()`
    does, which is the one thing that *must* differ between the children when the
    seeds differ. The `run` payload is one live `--bank --json` invocation against
    the shared fixtures, with the work root and the cwd (hence the default store
    `corpus/local`) redirected into the caller's tmp tree. Bytes go to
    `sys.stdout.buffer` so no encoding step or newline translation sits between
    the CLI's output and the comparison.
    """
    if payload == "probe":
        seen = tuple(hash(word) for word in ("plumb", "bank", "case"))
        sys.stdout.buffer.write(repr(seen).encode("utf-8"))
        sys.stdout.buffer.flush()
        return
    from plumb.cli import live, main

    live.WORK_ROOT = Path(work_root)
    os.chdir(cwd)
    code = main(["verify", str(PAPER), str(REPO), "--bindings", str(BINDINGS),
                 "--no-env-build", "--bank", "--json"])
    sys.stdout.buffer.flush()
    if code != 0:
        raise SystemExit(code)


# --------------------------------------------------------------------------------
# Spawning
# --------------------------------------------------------------------------------

_CHILD_PROGRAM = """\
import sys

# argv[1] is tests/cli: the child imports its entry point from the same module
# that will compare its output, so the two cannot drift apart.
sys.path.insert(0, sys.argv[1])

from test_bank_determinism import child_main

child_main(sys.argv[2], sys.argv[3], sys.argv[4])
"""


def run_child(
    payload: str,
    *,
    hash_seed: str,
    work_root: Path,
    cwd: Path,
) -> bytes:
    """Run one fresh interpreter under `hash_seed` and return its stdout bytes.

    `capture_output` without `text=`, so the bytes are never decoded and
    re-encoded. The seed goes through `env` rather than through an inherited
    variable, because inheritance is exactly the thing that would make every
    child agree for the wrong reason. `subprocess` is deliberately outside
    `conftest.py`'s network blocker — the blocker is a same-process guard and
    says so; nothing here reaches outward.
    """
    env = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        "PYTHONPATH": str(_SRC),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_PROGRAM, str(_THIS_DIR), payload,
         str(work_root), str(cwd)],
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"child failed (payload={payload!r}, seed={hash_seed!r}):\n"
        f"{result.stderr.decode('utf-8', 'replace')}"
    )
    assert isinstance(result.stdout, bytes)
    return result.stdout


def _banked_case_id(out: bytes) -> str:
    """The 64-hex case id the trailing `banked <case_id>` line names."""
    _document, tail = out.rsplit(b"banked ", 1)
    case_id = tail[:-1].decode("ascii")
    assert tail.endswith(b"\n"), f"banked line is not newline-terminated: {tail!r}"
    assert _HEX64.fullmatch(case_id), f"banked line names no case id: {tail!r}"
    return case_id


class TestTheSeedControl:
    """Proof that the seeds reach the children — without it, the identity is air."""

    def test_the_hash_seed_really_varies_in_the_child(self, tmp_path: Path) -> None:
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        probes = {
            seed: run_child("probe", hash_seed=seed, work_root=tmp_path / "work", cwd=cwd)
            for seed in FIXED_SEEDS
        }
        assert len(set(probes.values())) == len(FIXED_SEEDS), (
            "the children agree about hash() under different PYTHONHASHSEED values, "
            "so the seed is not reaching them and the byte-identity test below "
            f"proves nothing: {probes}"
        )


class TestTheBankedRunIsDeterministicAcrossProcessesAndSeeds:
    """Acceptance: two live `--bank --json` runs, fresh interpreters, varied seeds.

    The verdicts document is byte-identical; each run banks its own distinct
    case; the two cases differ only in `trace.json`'s wall-clock provenance.
    """

    def test_stdout_document_is_byte_identical_and_each_run_banked_its_own_case(
        self, tmp_path: Path
    ) -> None:
        work_root = tmp_path / "work"
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        outputs = {
            seed: run_child("run", hash_seed=seed, work_root=work_root, cwd=cwd)
            for seed in FIXED_SEEDS
        }
        documents: dict[str, bytes] = {}
        case_ids: dict[str, str] = {}
        for seed, out in outputs.items():
            document, _tail = out.rsplit(b"banked ", 1)
            documents[seed] = document
            case_ids[seed] = _banked_case_id(out)

        first, second, third = FIXED_SEEDS
        assert documents[second] == documents[first]
        assert documents[third] == documents[first]
        verdicts = json.loads(documents[first])
        assert verdicts["coverage"]["bound"] == 2

        assert len(set(case_ids.values())) == len(FIXED_SEEDS), (
            "the three runs banked the same case: the trace carries no wall-clock "
            "provenance, so the determinism test cannot distinguish them"
        )
        store = cwd / "corpus" / "local"
        assert sorted(p.name for p in store.iterdir()) == sorted(case_ids.values())

    def test_the_two_cases_differ_only_in_trace_provenance(
        self, tmp_path: Path
    ) -> None:
        work_root = tmp_path / "work"
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        case_ids = {
            seed: _banked_case_id(
                run_child("run", hash_seed=seed, work_root=work_root, cwd=cwd)
            )
            for seed in FIXED_SEEDS
        }
        store = cwd / "corpus" / "local"
        first, second, _third = FIXED_SEEDS
        case_a = store / case_ids[first]
        case_b = store / case_ids[second]

        for name in ("claims.json", "bindings.json", "verdicts.json"):
            assert (case_a / name).read_bytes() == (case_b / name).read_bytes(), (
                f"{name} differs between the two runs"
            )
        assert sorted(p.name for p in (case_a / "objects").iterdir()) == sorted(
            p.name for p in (case_b / "objects").iterdir()
        )

        raw_a = (case_a / "trace.json").read_bytes()
        raw_b = (case_b / "trace.json").read_bytes()
        assert raw_a != raw_b, "the two runs' traces are identical, so no provenance"
        trace_a = json.loads(raw_a)
        trace_b = json.loads(raw_b)
        for document in (trace_a, trace_b):
            document["started_at_ns"] = None
            for artifact in document["artifacts"]:
                artifact["mtime_ns"] = None
        assert trace_a == trace_b, (
            "the two traces differ beyond the wall-clock provenance fields "
            f"({_PROVENANCE_FIELDS})"
        )