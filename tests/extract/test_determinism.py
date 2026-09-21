"""The determinism controls, enforced by tests rather than by discipline.

Everything else in this aspect asserts determinism *within one process*. That is not
the claim being made. Inside a single interpreter, `dict` and `set` iteration order are
stable, so a single-process test passes happily while the contract is broken — the
bytes only diverge once a second process, with a different `PYTHONHASHSEED`, builds the
same document. So the load-bearing tests here spawn fresh interpreters and compare
their raw stdout **bytes**.

Four things this file is careful about, each of which has already bitten something:

- **The fixtures have one spelling.** The spawned interpreter imports this very module
  and calls `child_main`, so the claims the child serializes cannot drift from the ones
  the parent expects. A child with its own copy of the fixtures would eventually
  compare two different documents and call them equal.
- **The seed control.** A cross-seed identity test is worthless if the seed never
  reached the child. `test_the_hash_seed_really_varies_in_the_child` is the control: it
  asserts the children observably disagree about `hash()` under the seeds this file
  uses, so an identical serialized document is evidence about the serializer rather
  than evidence that the plumbing does nothing.
- **The source guard is structural, never textual.** The plan specified `grep` for
  `float(` under `src/plumb/extract/`. That guard is broken as specified: `value.py`'s
  module docstring contains the literal `float("0.1") + float("0.2") != 0.3` in the
  passage explaining why floats are forbidden, and the serialization work hit the same
  class of bug when `"environ"` matched the word "environment" in a docstring about not
  reading the environment. A guard that fires spuriously gets disabled, and then it
  never fires when it matters. So every guard below parses the module with `ast` and
  inspects real `Call`, `Import` and `ImportFrom` nodes; docstrings, comments and
  string literals are excluded structurally rather than by luck. Both directions are
  self-tested against synthetic modules, so the guard is known to fire *and* known not
  to misfire.
- **Vacuity.** A guard that scans nothing, or an assertion that holds because the thing
  it forbids could never appear, passes forever. The scans assert they found the
  modules; the path assertion asserts the document does contain a legitimate slash.

This module emits no verdicts. It pins the spine the verdict layer will later stand on.
"""

from __future__ import annotations

import ast
from decimal import Decimal
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from plumb.extract.claim import Claim
from plumb.extract.dedup import dedup_claims
from plumb.extract.hashing import hash_paper
from plumb.extract.location import CharSpan
from plumb.extract.serialize import serialize_claims
from plumb.extract.value import (
    Approximate,
    Bound,
    Interval,
    PlusMinus,
    Point,
    Range,
)

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[1]
_SRC = _REPO_ROOT / "src"
_PACKAGE = _SRC / "plumb" / "extract"


# --------------------------------------------------------------------------------
# The fixture corpus — built once, imported by both the parent and the child
# --------------------------------------------------------------------------------

#: CRLF and non-ASCII on purpose: the digest covers the *normalized* text, so a
#: checkout with different line endings must not produce a different document.
PAPER_TEXT = (
    "We report AUC 0.87 (95% CI [0.81, 0.93]) in the µ-cohort.\r\n"
    "Latency was 12 ms and the effect held at p < 0.001 (résumé, –).\n"
)


def sample_claims() -> tuple[Claim, ...]:
    """A corpus chosen to exercise every ordering decision at once.

    It contains claims that tie on the leading components of the sort key and can only
    be separated by the later ones: the same value at two precisions, the `None`/`""`
    units distinction, several mentions of one result, and one exact duplicate. A
    corpus whose claims all differ in their first field would be ordered correctly by
    almost any key, including a broken one.
    """
    auc = Point(text="0.87", value=Decimal("0.87"))
    return (
        Claim(
            reported_value=auc,
            units=None,
            metric="AUC",
            location=CharSpan(14, 18),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        # The same result, reported again elsewhere: one claim, two mentions.
        Claim(
            reported_value=auc,
            units=None,
            metric="AUC",
            location=CharSpan(120, 124),
            artifact_hint="results/eval.py::auc",
            tolerance_hint="within 0.01",
        ),
        # An exact duplicate of the first, down to the location.
        Claim(
            reported_value=auc,
            units=None,
            metric="AUC",
            location=CharSpan(14, 18),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        # Same number, different precision: two claims, not one.
        Claim(
            reported_value=Point(text="0.870", value=Decimal("0.870")),
            units=None,
            metric="AUC",
            location=CharSpan(14, 19),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        # `units=""` against `units=None` above: distinct records that tie on the
        # first two components of the sort key.
        Claim(
            reported_value=auc,
            units="",
            metric="AUC",
            location=CharSpan(14, 18),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        Claim(
            reported_value=auc,
            units="%",
            metric="AUC",
            location=CharSpan(14, 18),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        Claim(
            reported_value=Interval(
                text="95% CI [0.81, 0.93]",
                low=Decimal("0.81"),
                high=Decimal("0.93"),
            ),
            units=None,
            metric="AUC",
            location=CharSpan(20, 39),
            artifact_hint="results/eval.py::auc_ci",
            tolerance_hint=None,
        ),
        Claim(
            reported_value=PlusMinus(
                text="0.75 ± 0.03", center=Decimal("0.75"), margin=Decimal("0.03")
            ),
            units=None,
            metric="F1",
            location=CharSpan(60, 71),
            artifact_hint=None,
            tolerance_hint="±0.03",
        ),
        Claim(
            reported_value=Bound(text="p < 0.001", op="<", magnitude=Decimal("0.001")),
            units=None,
            metric="p-value",
            location=CharSpan(90, 99),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        Claim(
            reported_value=Range(text="12–15 %", low=Decimal("12"), high=Decimal("15")),
            units="%",
            metric="dropout rate",
            location=CharSpan(100, 107),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        Claim(
            reported_value=Approximate(text="~10,000", value=Decimal("10000")),
            units=None,
            metric="cohort size",
            location=CharSpan(108, 115),
            artifact_hint=None,
            tolerance_hint=None,
        ),
        Claim(
            reported_value=Point(text="12", value=Decimal("12")),
            units="ms",
            metric="latency",
            location=CharSpan(70, 72),
            artifact_hint="bench/latency.py::p50",
            tolerance_hint=None,
        ),
        # Non-ASCII in every string field, including a slash inside a unit — the
        # absolute-path guard below must not be a ban on slashes.
        Claim(
            reported_value=auc,
            units="µg/mL",
            metric="résumé µ-cohort AUC",
            location=CharSpan(45, 49),
            artifact_hint=None,
            tolerance_hint=None,
        ),
    )


#: Input orderings, each a permutation that depends on nothing but the index.
ORDERINGS = ("given", "reversed", "rotated", "interleaved")


def reorder(claims: tuple[Claim, ...], ordering: str) -> tuple[Claim, ...]:
    if ordering == "given":
        return claims
    if ordering == "reversed":
        return tuple(reversed(claims))
    if ordering == "rotated":
        return claims[5:] + claims[:5]
    if ordering == "interleaved":
        return claims[::2] + claims[1::2]
    raise ValueError(f"unknown ordering: {ordering!r}")


def render_dedup(claims: tuple[Claim, ...]) -> bytes:
    """A textual rendering of `dedup_claims` output, order included.

    Rendered rather than compared as records because the thing under test is the
    *order* of the merged claims and of the locations inside them — an equality check
    on a `tuple` would catch that too, but only after crossing a process boundary,
    which records do not do and bytes do.
    """
    lines = []
    for merged in dedup_claims(claims):
        locations = ";".join(
            f"{location.kind}:{location.start}-{location.end}"
            for location in merged.locations
        )
        lines.append(
            "|".join(
                (
                    merged.id,
                    merged.metric,
                    "<dimensionless>" if merged.units is None else merged.units,
                    merged.reported_value.text,
                    locations,
                    ";".join(merged.artifact_hints),
                    ";".join(merged.tolerance_hints),
                )
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def render(payload: str, ordering: str) -> bytes:
    """The bytes a child process is asked to produce.

    `probe` is the control payload: it reports what this interpreter's `hash()` does,
    which is the one thing that *must* differ between the children when the seeds
    differ. Without it, a cross-seed byte-identity pass could mean the serializer is
    deterministic or could mean `PYTHONHASHSEED` never arrived.
    """
    if payload == "probe":
        seen = tuple(hash(word) for word in ("plumb", "AUC", "0.87", "µg/mL"))
        return repr(seen).encode("utf-8")
    claims = reorder(sample_claims(), ordering)
    if payload == "claims":
        return serialize_claims(claims, paper_hash=hash_paper(PAPER_TEXT))
    if payload == "dedup":
        return render_dedup(claims)
    raise ValueError(f"unknown payload: {payload!r}")


def child_main(payload: str, ordering: str) -> None:
    """Entry point for the spawned interpreter: raw bytes to stdout, nothing else.

    Written to `sys.stdout.buffer` rather than `print`ed, so no encoding step and no
    newline translation sits between the serializer's bytes and the test's comparison.
    """
    sys.stdout.buffer.write(render(payload, ordering))
    sys.stdout.buffer.flush()


# --------------------------------------------------------------------------------
# Spawning
# --------------------------------------------------------------------------------

_CHILD_PROGRAM = """\
import sys

# argv[1] is tests/extract: the child imports the fixtures from the same module that
# will compare its output, so the two cannot drift apart.
sys.path.insert(0, sys.argv[1])

from test_determinism import child_main

child_main(sys.argv[2], sys.argv[3])
"""


def run_child(
    payload: str,
    ordering: str = "given",
    *,
    hash_seed: str,
    cwd: Path | None = None,
) -> bytes:
    """Run one fresh interpreter under `hash_seed` and return its stdout bytes.

    `capture_output` without `text=`, so the bytes are never decoded and re-encoded and
    a trailing newline is never translated away. The seed goes through `env` rather
    than through an inherited variable, because inheritance is exactly the thing that
    would make every child agree for the wrong reason.

    `subprocess` is deliberately outside `conftest.py`'s network blocker — the blocker
    is a same-process guard and says so. Nothing here reaches outward: a local
    interpreter is spawned and its stdout read.
    """
    env = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        # The child must import `plumb` however the parent found it.
        "PYTHONPATH": str(_SRC),
        # Leave no `__pycache__` behind in the tests tree.
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_PROGRAM, str(_THIS_DIR), payload, ordering],
        env=env,
        cwd=None if cwd is None else str(cwd),
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"child failed (payload={payload!r}, ordering={ordering!r}, "
        f"seed={hash_seed!r}):\n{result.stderr.decode('utf-8', 'replace')}"
    )
    assert isinstance(result.stdout, bytes)
    return result.stdout


#: Three fixed seeds and one genuinely random one. `0` disables hash randomization
#: entirely, `1` and `12345` enable it with fixed seeds, and `random` is what a user
#: actually runs under.
SEEDS = ("0", "1", "12345", "random")
FIXED_SEEDS = ("0", "1", "12345")


# --------------------------------------------------------------------------------
# The load-bearing tests
# --------------------------------------------------------------------------------


class TestTheSeedControl:
    """Proof that the seeds reach the children — without it, everything below is air."""

    def test_the_hash_seed_really_varies_in_the_child(self) -> None:
        probes = {seed: run_child("probe", hash_seed=seed) for seed in FIXED_SEEDS}
        distinct = set(probes.values())
        assert len(distinct) == len(FIXED_SEEDS), (
            "the children agree about hash() under different PYTHONHASHSEED values, "
            "so the seed is not reaching them and the byte-identity tests below "
            f"prove nothing: {probes}"
        )

    def test_the_child_really_is_a_separate_process(self) -> None:
        # A "child" that was somehow this interpreter would inherit this process's
        # seed, and every comparison below would hold for the wrong reason.
        here = render("probe", "given")
        elsewhere = {run_child("probe", hash_seed=seed) for seed in FIXED_SEEDS}
        assert any(probe != here for probe in elsewhere)


class TestCrossProcessByteIdentity:
    """The same claims, in fresh interpreters, produce the same bytes.

    This is the test the whole aspect rests on. Every other determinism assertion in
    this suite runs inside one process, where `dict` and `set` iteration order are
    stable — so they pass while the contract is broken.
    """

    def test_the_bytes_are_identical_across_hash_seeds(self) -> None:
        outputs = {seed: run_child("claims", hash_seed=seed) for seed in SEEDS}
        distinct = set(outputs.values())
        assert len(distinct) == 1, (
            "serialize_claims produced different bytes under different "
            f"PYTHONHASHSEED values: { {s: len(o) for s, o in outputs.items()} }"
        )

    def test_the_child_bytes_match_this_process(self) -> None:
        # Ties the cross-process claim to the in-process one: the children are not
        # merely consistent with each other, they agree with the serializer as this
        # interpreter runs it.
        expected = serialize_claims(sample_claims(), paper_hash=hash_paper(PAPER_TEXT))
        assert run_child("claims", hash_seed="12345") == expected

    def test_the_output_is_non_empty_and_carries_the_corpus(self) -> None:
        # Vacuity control: two empty documents are also byte-identical.
        out = run_child("claims", hash_seed="1")
        assert len(out) > 200
        assert out.count(b'"id":') == len(sample_claims())

    def test_the_trailing_newline_survives_the_pipe(self) -> None:
        # The plumbing trap named in the plan: a shell, a `text=True` capture or a
        # `print` round-trip each quietly strip or translate this byte.
        out = run_child("claims", hash_seed="1")
        assert out.endswith(b"}\n")
        assert not out.endswith(b"\n\n")
        assert b"\r" not in out

    def test_the_output_is_bytes_not_text(self) -> None:
        out = run_child("claims", hash_seed="1")
        assert isinstance(out, bytes)
        # Decodable, but the comparison above is made on the bytes; asserting on the
        # decoded string would leave the encoding unpinned.
        assert "µg/mL" in out.decode("utf-8")


class TestInputOrderIndependenceAcrossProcesses:
    """Extraction order must not survive into the document, in any process.

    Each ordering runs under a *different* seed, so input order and hash order vary at
    the same time. A serializer that leaned on either one would break here.
    """

    def test_every_input_order_gives_the_same_bytes(self) -> None:
        outputs = {
            ordering: run_child("claims", ordering, hash_seed=seed)
            for ordering, seed in zip(ORDERINGS, SEEDS)
        }
        assert len(set(outputs.values())) == 1, (
            "input order changed the serialized bytes across processes: "
            f"{ {o: len(b) for o, b in outputs.items()} }"
        )

    def test_the_orderings_are_really_different(self) -> None:
        # Vacuity control: if `reorder` returned its input, the test above would be
        # comparing four identical inputs.
        claims = sample_claims()
        permutations = {
            ordering: tuple(
                (c.id, c.location.start) for c in reorder(claims, ordering)
            )
            for ordering in ORDERINGS
        }
        assert len(set(permutations.values())) == len(ORDERINGS)
        for ordering in ORDERINGS:
            assert sorted(permutations[ordering]) == sorted(permutations["given"])

    def test_dedup_order_is_identical_across_processes_and_input_orders(self) -> None:
        # Dedup groups by identity through a `dict`, and merges locations and hints.
        # Group order, member order and location order are each a place where hash or
        # arrival order could leak out, and none of them is visible in one process.
        outputs = {
            ordering: run_child("dedup", ordering, hash_seed=seed)
            for ordering, seed in zip(ORDERINGS, SEEDS)
        }
        assert len(set(outputs.values())) == 1, (
            f"dedup output depended on input order or hash seed: {outputs}"
        )

    def test_dedup_output_is_non_empty_and_actually_merged(self) -> None:
        out = run_child("dedup", hash_seed="1").decode("utf-8")
        rows = out.strip().split("\n")
        assert 0 < len(rows) < len(sample_claims()), "nothing merged; test is vacuous"
        # The AUC claim was reported at two distinct spans and duplicated at one of
        # them: two locations on one row, not three.
        assert any(row.count(";") >= 1 and "char_span:14-18" in row for row in rows)


class TestNoAmbientStateInTheOutput:
    """D1: determinism comes from *not having* sources of nondeterminism.

    A timestamp scrubbed from the output is still a timestamp that was generated, and
    the next field added will not be scrubbed. These assertions are made on the
    document's content rather than on paths compared to paths: `Path.resolve()` differs
    from the path you started with whenever a symlink is involved (`/tmp` resolves to
    `/private/tmp` on this platform), so a path-equality assertion would be testing the
    filesystem rather than the serializer.
    """

    #: Shapes, not values. A literal "now" would be missed by an equality assertion
    #: written when the test ran.
    TIMESTAMP_SHAPES = (
        rb"\d{4}-\d{2}-\d{2}",  # 2026-09-21
        rb"\d{2}:\d{2}:\d{2}",  # 14:03:55
        rb"\d{4}\d{2}\d{2}T\d{2}",  # 20260921T14
    )

    #: Two segments, because one slash is legitimate: `µg/mL` is a unit.
    ABSOLUTE_PATH_SHAPES = (
        rb"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
        rb"[A-Za-z]:\\",
    )

    def _document(self) -> bytes:
        return serialize_claims(sample_claims(), paper_hash=hash_paper(PAPER_TEXT))

    def test_no_timestamp_shaped_content(self) -> None:
        out = self._document()
        for shape in self.TIMESTAMP_SHAPES:
            found = re.search(shape, out)
            assert found is None, f"timestamp-shaped content in output: {found!r}"

    def test_no_absolute_path_shaped_content(self) -> None:
        out = self._document()
        # Vacuity control: the document *does* contain a slash, so the assertion below
        # is not passing merely because no slash could ever appear. A guard that bans
        # slashes outright would fail on this unit and promptly be deleted.
        assert "µg/mL".encode("utf-8") in out
        for shape in self.ABSOLUTE_PATH_SHAPES:
            found = re.search(shape, out)
            assert found is None, f"path-shaped content in output: {found!r}"

    def test_no_machine_specific_string_reaches_the_output(self, tmp_path: Path) -> None:
        out = self._document()
        ambient = {
            str(Path.cwd()),
            str(Path.cwd().resolve()),
            str(tmp_path),
            str(tmp_path.resolve()),
            str(Path.home()),
            str(_REPO_ROOT),
            sys.executable,
            sys.prefix,
        }
        for value in ambient:
            assert value.encode("utf-8") not in out, f"{value!r} reached the output"

    def test_the_output_does_not_depend_on_the_working_directory(
        self, tmp_path: Path
    ) -> None:
        # The honest form of "no absolute path": run two children from different
        # directories and compare. Nothing here compares a path to a path, so the
        # symlink question never arises.
        from_repo = run_child("claims", hash_seed="1", cwd=_REPO_ROOT)
        from_tmp = run_child("claims", hash_seed="12345", cwd=tmp_path)
        assert from_repo == from_tmp

    def test_the_paper_hash_is_over_normalized_text_not_the_raw_bytes(self) -> None:
        # A checkout's line endings are ambient state too: the same paper on a Windows
        # checkout must name itself with the same digest.
        crlf = PAPER_TEXT.replace("\n", "\r\n").replace("\r\r\n", "\r\n")
        assert crlf != PAPER_TEXT
        assert hash_paper(crlf) == hash_paper(PAPER_TEXT)


# --------------------------------------------------------------------------------
# The source-level guard
# --------------------------------------------------------------------------------


def module_sources() -> dict[str, str]:
    """Every module of the package, by name, read as text."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_PACKAGE.rglob("*.py"))
    }


def called_names(tree: ast.Module) -> set[str]:
    """The names of everything actually *called*, from `Call` nodes only.

    `float` in an annotation, `float` named inside `isinstance(x, float)` — which is a
    check that *rejects* floats — and `float(` inside a docstring are all excluded by
    construction, because none of them is a `Call` whose target is `float`.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return names


def imported_roots(tree: ast.Module) -> set[str]:
    """The top-level package of every import, from import nodes only."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def read_attributes(tree: ast.Module) -> set[str]:
    """Attribute names read anywhere — `os.environ` is a read, not a call."""
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def set_iterations(tree: ast.Module) -> list[str]:
    """Places that iterate a set *directly*, which is hash-ordered.

    Only the unambiguous shapes: `for x in {...}` / `for x in set(...)` and the same
    inside a comprehension. `sorted(set(...))` is fine and is not flagged, because the
    iteration order of the set never reaches the output. Anything subtler than this is
    undecidable from the syntax, so it is left to review rather than guessed at —
    a guess here would be the spurious failure that gets the whole guard switched off.
    """
    def is_set(node: ast.expr) -> bool:
        if isinstance(node, ast.Set) or isinstance(node, ast.SetComp):
            return True
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"set", "frozenset"}
        )

    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)) and is_set(node.iter):
            found.append(f"line {node.lineno}: for-loop over a set")
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for generator in node.generators:
                if is_set(generator.iter):
                    found.append(f"line {node.lineno}: comprehension over a set")
    return found


class TestTheGuardItself:
    """The guard is tested before it is trusted, in both directions.

    A guard is only worth having if it fires on the thing it forbids and stays silent
    on the thing it does not. The synthetic modules below pin both halves, so neither
    can rot: the negative control is a module whose *prose* is full of the forbidden
    words, which is exactly the shape that broke the `grep` this replaced.
    """

    POSITIVE = '''\
"""A module that really does the forbidden things."""
import datetime
from random import shuffle
import os
from pathlib import Path


def go(raw, claims):
    when = datetime.datetime.now()
    here = os.getcwd()
    there = Path(raw).resolve()
    for claim in set(claims):
        print(float(raw), hash(claim), os.environ.get("HOME"))
    return when, here, there
'''

    NEGATIVE = '''\
"""Why this module never calls float(0.1) or hash(x).

`float("0.1") + float("0.2") != 0.3`, and `hash()` varies with PYTHONHASHSEED, so
neither may decide anything here. It also reads no environment: os.environ, getcwd()
and datetime.now() are all out, and `import random` would be too.
"""

FORBIDDEN = ("float(", "hash(", "os.getcwd()", "datetime.now()", "import uuid")


def check(value):
    # A type check that *rejects* a float is not a call to float.
    if isinstance(value, float):
        raise TypeError("no floats: see " + FORBIDDEN[0])
    return sorted({value})
'''

    def test_it_fires_on_a_module_that_does_the_forbidden_things(self) -> None:
        tree = ast.parse(self.POSITIVE)
        assert {"float", "hash", "getcwd", "resolve", "now"} <= called_names(tree)
        assert {"datetime", "random", "os", "pathlib"} <= imported_roots(tree)
        assert "environ" in read_attributes(tree)
        assert set_iterations(tree)

    def test_it_stays_silent_on_prose_about_the_forbidden_things(self) -> None:
        # This is the case the `grep` guard the plan specified gets wrong: every
        # forbidden token appears in this module as text, and none of it is code.
        assert 'float("0.1")' in self.NEGATIVE
        assert "import uuid" in self.NEGATIVE
        tree = ast.parse(self.NEGATIVE)
        assert not (called_names(tree) & FORBIDDEN_CALLS)
        assert not (imported_roots(tree) & FORBIDDEN_IMPORTS)
        assert "environ" not in read_attributes(tree)
        assert set_iterations(tree) == []

    def test_sorted_around_a_set_is_not_flagged(self) -> None:
        # `sorted(set(...))` is deterministic; flagging it would be the spurious
        # failure that gets the guard disabled.
        tree = ast.parse("for x in sorted(set(y)):\n    print(x)\n")
        assert set_iterations(tree) == []


#: Modules whose mere presence is a determinism hazard in this layer.
FORBIDDEN_IMPORTS = frozenset(
    {
        "datetime",
        "locale",
        "os",
        "pathlib",
        "platform",
        "random",
        "secrets",
        "socket",
        "subprocess",
        "tempfile",
        "time",
        "uuid",
    }
)

#: Calls that read ambient state, plus the two the record layer has already been
#: bitten by: `float(` (risk R2, `docs/ROADMAP.md:57`) and bare `hash(`, whose result
#: varies with `PYTHONHASHSEED` from one process to the next.
FORBIDDEN_CALLS = frozenset(
    {
        "choice",
        "float",
        "getcwd",
        "getenv",
        "hash",
        "monotonic",
        "now",
        "perf_counter",
        "resolve",
        "sample",
        "shuffle",
        "time",
        "today",
        "uuid4",
    }
)

#: Everything the package is allowed to import. An allowlist rather than only a
#: denylist, because a denylist can only ever forbid the hazards someone thought of;
#: this fails on `import getpass` too. Adding a line here is a deliberate, reviewable
#: act — which is the point — and the failure message says so.
ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "abc",
        "collections",
        "dataclasses",
        "decimal",
        "hashlib",
        "json",
        "plumb",
        "re",
        "typing",
        "unicodedata",
    }
)


class TestNoModuleInThePackageReadsAmbientState:
    """The repo-wide version of the guard `test_serialize.py` applies to one module.

    Every check here parses the module and inspects real nodes. Nothing matches on
    text: `value.py`'s docstring contains `float("0.1") + float("0.2") != 0.3` in the
    passage explaining why floats are banned, so a `grep` for `float(` fails on the
    very file that documents the rule — and a guard that fires spuriously gets
    disabled, after which it never fires when it matters.
    """

    def test_the_scan_actually_covers_the_package(self) -> None:
        # Vacuity control: a guard that scans nothing passes forever.
        names = set(module_sources())
        assert {
            "__init__.py",
            "claim.py",
            "dedup.py",
            "hashing.py",
            "location.py",
            "serialize.py",
            "value.py",
        } <= names

    def test_no_module_calls_anything_that_reads_ambient_state(self) -> None:
        offenders = {
            name: sorted(called_names(ast.parse(source)) & FORBIDDEN_CALLS)
            for name, source in module_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}

    def test_no_module_imports_a_source_of_nondeterminism(self) -> None:
        offenders = {
            name: sorted(imported_roots(ast.parse(source)) & FORBIDDEN_IMPORTS)
            for name, source in module_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}

    def test_no_module_imports_outside_the_deterministic_allowlist(self) -> None:
        offenders = {
            name: sorted(imported_roots(ast.parse(source)) - ALLOWED_IMPORTS)
            for name, source in module_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}, (
            "an import outside the allowlist: confirm it reads no clock, no "
            "environment, no filesystem and no randomness, then add it to "
            "ALLOWED_IMPORTS in this file."
        )

    def test_no_module_reads_the_environment(self) -> None:
        # `os.environ` is an attribute read, not a call, so the call guard above would
        # miss it. Matched as an attribute node — the word "environment" in a docstring
        # cannot reach this, which is the bug the serialization work already hit.
        offenders = [
            name
            for name, source in module_sources().items()
            if "environ" in read_attributes(ast.parse(source))
        ]
        assert offenders == []

    def test_no_module_iterates_a_set_directly(self) -> None:
        offenders = {
            name: set_iterations(ast.parse(source))
            for name, source in module_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}


class TestLineEndingsArePinned:
    """Character offsets are machine-dependent without this.

    `CharSpan` indexes the normalized text, and normalization turns CRLF into LF — but
    a checkout that materializes CRLF still hands a different *raw* file to intake, and
    every offset a reviewer checks by hand against the file on disk shifts by one per
    preceding line. The setting was pulled forward in aspect 1; assert it rather than
    assume it.
    """

    def test_gitattributes_exists(self) -> None:
        assert (_REPO_ROOT / ".gitattributes").is_file(), (
            f"no .gitattributes at {_REPO_ROOT}"
        )

    def test_gitattributes_pins_lf_for_every_file(self) -> None:
        content = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
        universal = [
            line
            for line in content.splitlines()
            if line.split()[:1] == ["*"] and "eol=lf" in line
        ]
        assert universal, (
            "no `* ... eol=lf` line in .gitattributes: without it a checkout can "
            f"materialize CRLF and shift every character offset. Got:\n{content}"
        )


@pytest.mark.parametrize("seed", FIXED_SEEDS)
def test_a_single_claim_is_byte_identical_across_processes(seed: str) -> None:
    """Each fixed seed against a genuinely randomized one, one seed per failure.

    Kept separate from the corpus test so a failure names the seed rather than the
    set. The baseline is `random` rather than a fixed seed on purpose: comparing seed
    `0` against seed `0` would be two processes that agree because nothing varied.
    """
    assert run_child("claims", hash_seed=seed) == run_child(
        "claims", hash_seed="random"
    )
