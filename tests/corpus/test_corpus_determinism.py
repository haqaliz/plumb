"""The corpus store's determinism controls, enforced by tests (Phase 3).

Acceptance criteria 1, 6 and 8 of `docs/planning/discrepancy-corpus/store/spec.md`,
in the `tests/extract/test_determinism.py` shape: every assertion above runs
inside one interpreter, where `dict` and `set` iteration order are stable — so
they pass while the contract is broken. The load-bearing tests here spawn fresh
interpreters under different `PYTHONHASHSEED` values and compare raw stdout
**bytes**.

Four things this file is careful about, each inherited from the extract suite:

- **The fixtures have one spelling.** The spawned interpreter imports this very
  module and calls `child_main`, so the record the child banks cannot drift from
  the one the parent expects. The record itself is a *deterministic record*: a
  real C3 run (`run_full`) whose provenance — `started_at_ns` and artifact
  `mtime_ns`, which `run/trace.py` documents as provenance, not identity — is
  pinned to a fixed value. Two runs on one machine differ only there, so the
  pinned record is the same bytes in every process, and the manifest and the
  case tree derived from it are comparable.
- **The seed control.** A cross-seed identity test is worthless if the seed never
  reached the child. `test_the_hash_seed_really_varies_in_the_child` is the
  control: the children must observably disagree about `hash()` under the seeds
  this file uses.
- **The source guard is structural, never textual.** Every guard parses the
  module with `ast`; docstrings, comments and string literals are excluded
  structurally, as are type annotations and `isinstance(v, float)` checks.
  The guard matches *references*, not calls: `json.dumps(default=float)` converts
  every `Decimal` without ever calling `float`. Both directions are self-tested
  against synthetic modules, and a mutation check edits a real module and proves
  the scan would flag it.
- **The division of labour between the two guards.** The source scan reads
  `src/plumb/corpus/` and nothing else, so member bytes arriving from a caller —
  the store treats them as opaque — are outside every AST check. The manifest's
  key set is pinned for exactly that case: `TestTheManifestSchemaIsClosed` fails
  on any field that appears unannounced, whatever it contains.

This module banks no real cases. It pins the bytes the bank and benchmark
aspects will stand on.
"""

from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from plumb.corpus import bank_case
from plumb.corpus.case import parse_case
from plumb.extract.hashing import PaperHash
from plumb.extract.serialize import serialize_claims
from plumb.run.trace import serialize_trace
from plumb.verify import Completed, serialize_verdicts, verify_claims
from plumb.verify.bindings import load_bindings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "verify"))
from verify_helpers import bindings_json, claim, run_full, writes  # noqa: E402
from record_helpers import DEFAULT_PAPER, nonclaims_json, record_dir  # noqa: E402

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[1]
_SRC = _REPO_ROOT / "src"
_PACKAGE = _SRC / "plumb" / "corpus"

#: The provenance stamp every deterministic record shares. `started_at_ns` and
#: artifact `mtime_ns` are recorded for diagnosis, never for identity
#: (`run/trace.py`), so two runs of one program differ only here.
_FIXED_NS = 1_700_000_000_000_000_000

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

PAPER = DEFAULT_PAPER


def deterministic_record(root: Path) -> Path:
    """A record whose bytes cannot vary between processes.

    A real C3 run (`run_full`), with the provenance fields pinned after it —
    every other byte stays the real run's. The verdicts then derive from fixed
    bytes, so the record, the manifest and the case tree are the same bytes in
    every process, whatever its `PYTHONHASHSEED`.
    """
    paper_claim = claim("0.87")
    _, _result, capture, trace = run_full(root, writes("results.json", '{"auc": 0.8712}'))
    trace = replace(
        trace,
        started_at_ns=_FIXED_NS,
        artifacts=tuple(
            replace(a, mtime_ns=_FIXED_NS if a.mtime_ns is not None else None)
            for a in trace.artifacts
        ),
    )
    bindings_bytes = bindings_json(
        (paper_claim, "results.json", {"kind": "json_pointer", "pointer": "/auc"})
    )
    verdicts = verify_claims(
        [paper_claim],
        load_bindings(bindings_bytes, [paper_claim.id]),
        Completed(trace, capture),
    )
    record = root / "record"
    (record / "objects").mkdir(parents=True)
    for path in capture.store.iterdir():
        (record / "objects" / path.name).write_bytes(path.read_bytes())
    digest = hashlib.sha256(PAPER).hexdigest()
    (record / "claims.json").write_bytes(
        serialize_claims([paper_claim], paper_hash=PaperHash(digest=digest))
    )
    (record / "bindings.json").write_bytes(bindings_bytes)
    (record / "trace.json").write_bytes(serialize_trace(trace))
    (record / "verdicts.json").write_bytes(serialize_verdicts(verdicts))
    (record / "paper.md").write_bytes(PAPER)
    return record


def render_tree(case_dir: Path) -> bytes:
    """The whole case tree as one deterministic text rendering, order included.

    Rendered rather than compared as a file walk, because the thing under test
    is the *bytes*: each file's name (sorted) and its content hex — no dict or
    set iteration survives into the output, and none may either.
    """
    lines = []
    for path in sorted(case_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(case_dir).as_posix()
            lines.append(f"{rel}:{path.read_bytes().hex()}")
    return ("\n".join(lines) + "\n").encode("utf-8")


# --------------------------------------------------------------------------------
# Spawning
# --------------------------------------------------------------------------------

_CHILD_PROGRAM = """\
import sys

# argv[1] is tests/corpus: the child imports the fixtures from the same module
# that will compare its output, so the two cannot drift apart.
sys.path.insert(0, sys.argv[1])

from test_corpus_determinism import child_main

child_main(sys.argv[2], sys.argv[3])
"""


def run_child(
    payload: str,
    *,
    hash_seed: str,
    out_dir: Path,
) -> bytes:
    """Run one fresh interpreter under `hash_seed` and return its stdout bytes.

    `capture_output` without `text=`, so the bytes are never decoded and
    re-encoded and a trailing newline is never translated away. The seed goes
    through `env` rather than through an inherited variable, because inheritance
    is exactly the thing that would make every child agree for the wrong reason.

    `subprocess` is deliberately outside `conftest.py`'s network blocker — the
    blocker is a same-process guard and says so. Nothing here reaches outward:
    a local interpreter is spawned and its stdout read.
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
        [sys.executable, "-c", _CHILD_PROGRAM, str(_THIS_DIR), payload, str(out_dir)],
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


#: Three fixed seeds and one genuinely random one. `0` disables hash randomization
#: entirely, `1` and `12345` enable it with fixed seeds, and `random` is what a
#: user actually runs under.
SEEDS = ("0", "1", "12345", "random")
FIXED_SEEDS = ("0", "1", "12345")


# --------------------------------------------------------------------------------
# The load-bearing tests
# --------------------------------------------------------------------------------


class TestTheSeedControl:
    """Proof that the seeds reach the children — without it, everything below is air."""

    def test_the_hash_seed_really_varies_in_the_child(self, tmp_path: Path) -> None:
        probes = {
            seed: run_child("probe", hash_seed=seed, out_dir=tmp_path / f"probe-{seed}")
            for seed in FIXED_SEEDS
        }
        distinct = set(probes.values())
        assert len(distinct) == len(FIXED_SEEDS), (
            "the children agree about hash() under different PYTHONHASHSEED values, "
            "so the seed is not reaching them and the byte-identity tests below "
            f"prove nothing: {probes}"
        )

    def test_the_child_really_is_a_separate_process(self, tmp_path: Path) -> None:
        # A "child" that was somehow this interpreter would inherit this process's
        # seed, and every comparison below would hold for the wrong reason.
        here = render("probe", out_dir=tmp_path / "here")
        elsewhere = {
            run_child("probe", hash_seed=seed, out_dir=tmp_path / f"else-{seed}")
            for seed in FIXED_SEEDS
        }
        assert any(probe != here for probe in elsewhere)


class TestCrossProcessByteIdentity:
    """The same record, in fresh interpreters, produces the same bytes.

    This is the test the whole aspect rests on. Every other determinism
    assertion in this suite runs inside one process, where `dict` and `set`
    iteration order are stable — so they pass while the contract is broken.
    """

    def test_the_manifest_bytes_are_identical_across_hash_seeds(
        self, tmp_path: Path
    ) -> None:
        outputs = {
            seed: run_child("manifest", hash_seed=seed, out_dir=tmp_path / f"m-{seed}")
            for seed in SEEDS
        }
        distinct = set(outputs.values())
        assert len(distinct) == 1, (
            "case.json produced different bytes under different PYTHONHASHSEED "
            f"values: { {s: len(o) for s, o in outputs.items()} }"
        )

    def test_the_case_tree_bytes_are_identical_across_hash_seeds(
        self, tmp_path: Path
    ) -> None:
        outputs = {
            seed: run_child("case", hash_seed=seed, out_dir=tmp_path / f"c-{seed}")
            for seed in SEEDS
        }
        distinct = set(outputs.values())
        assert len(distinct) == 1, (
            "the banked case tree produced different bytes under different "
            f"PYTHONHASHSEED values: { {s: len(o) for s, o in outputs.items()} }"
        )

    def test_the_child_manifest_matches_this_process(self, tmp_path: Path) -> None:
        # Ties the cross-process claim to the in-process one: the children are
        # not merely consistent with each other, they agree with the store as
        # this interpreter runs it.
        expected = render("manifest", out_dir=tmp_path / "parent")
        assert run_child("manifest", hash_seed="12345", out_dir=tmp_path / "child") == expected

    def test_the_case_output_is_non_empty_and_carries_the_case(
        self, tmp_path: Path
    ) -> None:
        # Vacuity control: two empty documents are also byte-identical.
        out = run_child("case", hash_seed="1", out_dir=tmp_path / "full")
        assert len(out) > 500
        assert b"case.json:" in out
        assert b"trace.json:" in out
        assert b"objects/" in out
        assert b"paper.md:" in out

    def test_the_trailing_newline_survives_the_pipe(self, tmp_path: Path) -> None:
        # The plumbing trap named in the plan: a shell, a `text=True` capture or
        # a `print` round-trip each quietly strip or translate this byte.
        out = run_child("manifest", hash_seed="1", out_dir=tmp_path / "nl")
        assert out.endswith(b"}\n")
        assert not out.endswith(b"\n\n")
        assert b"\r" not in out

    def test_the_output_is_bytes_not_text(self, tmp_path: Path) -> None:
        out = run_child("manifest", hash_seed="1", out_dir=tmp_path / "raw")
        assert isinstance(out, bytes)
        # Decodable, but the comparison above is made on the bytes; asserting on
        # the decoded string would leave the encoding unpinned.
        assert "plumb-corpus-case/1" in out.decode("utf-8")


def render(payload: str, out_dir: Path) -> bytes:
    """The bytes a child process is asked to produce.

    `probe` is the control payload: it reports what this interpreter's `hash()`
    does, which is the one thing that *must* differ between the children when
    the seeds differ. Without it, a cross-seed byte-identity pass could mean the
    store is deterministic or could mean `PYTHONHASHSEED` never arrived.
    """
    if payload == "probe":
        seen = tuple(hash(word) for word in ("plumb", "case", "run", "µg/mL"))
        return repr(seen).encode("utf-8")
    if payload in {"manifest", "case"}:
        record = deterministic_record(out_dir / "record")
        case = bank_case(record, out_dir / "store")
        case_dir = out_dir / "store" / case.case_id
        if payload == "manifest":
            return (case_dir / "case.json").read_bytes()
        return render_tree(case_dir)
    raise ValueError(f"unknown payload: {payload!r}")


def child_main(payload: str, out_dir: str) -> None:
    """Entry point for the spawned interpreter: raw bytes to stdout, nothing else.

    Written to `sys.stdout.buffer` rather than `print`ed, so no encoding step
    and no newline translation sits between the bytes and the test's comparison.
    """
    sys.stdout.buffer.write(render(payload, Path(out_dir)))
    sys.stdout.buffer.flush()


# --------------------------------------------------------------------------------
# The manifest schema, closed
# --------------------------------------------------------------------------------


def json_key_paths(node: object, prefix: str = "") -> set[str]:
    """Every key in the document, path-qualified — `member_hashes.claims`.

    Path-qualified rather than a flat set of names, so a field that *moves* is
    an unexpected key too: `case_id` at the top level and `case_id` inside
    `member_hashes` are different facts, and a bare name set would let one
    migrate into the other unnoticed.
    """
    paths: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths |= json_key_paths(value, path)
    elif isinstance(node, list):
        for item in node:
            paths |= json_key_paths(item, f"{prefix}[]")
    return paths


#: Every key the manifest is allowed to contain. This is the schema the bank
#: aspect's consumers replay; adding a line here is a contract change.
MANIFEST_SCHEMA = frozenset(
    {
        "case_id",
        "format",
        "has_labels",
        "labels_hash",
        "member_hashes",
        "member_hashes.bindings",
        "member_hashes.claims",
        "member_hashes.nonclaims",
        "member_hashes.trace",
        "member_hashes.verdicts",
        "objects_tree_hash",
        "paper_hash",
        "run_id",
    }
)


class TestTheManifestSchemaIsClosed:
    """No field reaches the manifest unannounced — whatever it happens to contain.

    **This is the half of the guard that covers what the source scan cannot.**
    The AST guards below read `src/plumb/corpus/` only, so a value arriving
    through a caller-supplied parameter — member bytes the store treats as
    opaque — is outside every one of them. So the manifest's key set is pinned
    instead, catching the unannounced field regardless of what is in it: a
    clock, an epoch integer, a path, a machine name.
    """

    def _documents(self, tmp_path: Path) -> dict[str, dict[str, object]]:
        fixtures = {
            "plain": record_dir(tmp_path / "plain"),
            "nonclaims": record_dir(tmp_path / "nonclaims", nonclaims=nonclaims_json()),
            "paperless": record_dir(tmp_path / "paperless", paper=None),
            "labeled": record_dir(tmp_path / "labeled"),
        }
        documents = {}
        for name, record in fixtures.items():
            labels = {"c1": "confirmed"} if name == "labeled" else None
            case = bank_case(record, tmp_path / "store" / name, labels=labels)
            raw = (tmp_path / "store" / name / case.case_id / "case.json").read_bytes()
            parsed = json.loads(raw.decode("utf-8"))
            assert isinstance(parsed, dict)
            documents[name] = parsed
        return documents

    def test_every_key_in_the_manifest_is_declared(self, tmp_path: Path) -> None:
        unexpected = sorted(
            set().union(
                *(json_key_paths(doc) - MANIFEST_SCHEMA for doc in self._documents(tmp_path).values())
            )
        )
        assert not unexpected, (
            f"undeclared key(s) in the manifest: {unexpected}. A new field is a "
            "change to the manifest contract the bank and benchmark aspects "
            "read — not a test to be silenced. If the field belongs in the "
            "contract, add it to MANIFEST_SCHEMA in this file deliberately, and "
            "check it carries no clock, path, hostname or other ambient state, "
            "because no source guard can see a value that arrives from a caller."
        )

    def test_every_declared_key_is_actually_produced(self, tmp_path: Path) -> None:
        # Keeps the allowlist honest in the other direction: a declared key
        # nothing produces is a line someone can hide a future field behind.
        produced = set().union(
            *(json_key_paths(doc) for doc in self._documents(tmp_path).values())
        )
        missing = sorted(MANIFEST_SCHEMA - produced)
        assert not missing, (
            f"declared but never produced: {missing}. Either the fixtures stopped "
            "covering a variant (the nonclaims lane?), or MANIFEST_SCHEMA carries "
            "a stale line."
        )

    def test_the_key_scan_sees_a_field_added_anywhere(self, tmp_path: Path) -> None:
        # The guard tested before it is trusted, at each depth a field could appear.
        document = self._documents(tmp_path)["plain"]
        assert "banked_at" not in json_key_paths(document)

        top = {**document, "banked_at": "2026-10-01T09:00:00"}
        assert "banked_at" in json_key_paths(top) - MANIFEST_SCHEMA

        nested = {**document, "member_hashes": {**document["member_hashes"], "seen_at": "0"}}
        assert "member_hashes.seen_at" in json_key_paths(nested) - MANIFEST_SCHEMA

    def test_a_field_that_moved_is_unexpected_too(self, tmp_path: Path) -> None:
        # Path-qualified keys: `case_id` is legal at the top level and illegal
        # inside member_hashes. A flat name set would not notice.
        document = self._documents(tmp_path)["plain"]
        moved = {**document, "member_hashes": {"case_id": document["case_id"]}}
        assert "member_hashes.case_id" in json_key_paths(moved)
        assert "member_hashes.case_id" not in MANIFEST_SCHEMA

    def test_a_manifest_without_labels_hash_is_refused(self, tmp_path: Path) -> None:
        # `labels_hash` is in the manifest contract from Phase 1 on; a manifest
        # that predates it (or dropped it) must not parse into a Case.
        case = bank_case(record_dir(tmp_path / "record"), tmp_path / "store")
        case_dir = tmp_path / "store" / case.case_id
        document = json.loads((case_dir / "case.json").read_bytes())
        del document["labels_hash"]
        forged = (json.dumps(document, **_JSON) + "\n").encode("utf-8")
        with pytest.raises(ValueError, match="labels_hash"):
            parse_case(forged)


# --------------------------------------------------------------------------------
# The source-level guard
# --------------------------------------------------------------------------------


def module_sources() -> dict[str, str]:
    """Every module of the package, by name, read as text."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_PACKAGE.rglob("*.py"))
    }


def _exempt_nodes(tree: ast.Module) -> set[ast.AST]:
    """Subtrees where a forbidden name is not a hazard, excluded structurally.

    - **Annotations.** `def f(x: int | str | float) -> float` names a type, it
      does not convert anything.
    - **`isinstance(value, float)` and `issubclass`.** In this codebase that is
      the shape of a check that *rejects* floats — the opposite of the hazard.
    """
    exempt: set[ast.AST] = set()

    def skip(node: ast.expr | None) -> None:
        if node is not None:
            exempt.update(ast.walk(node))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            skip(node.returns)
        elif isinstance(node, (ast.arg, ast.AnnAssign)):
            skip(node.annotation)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"isinstance", "issubclass"}
        ):
            for argument in node.args[1:]:
                skip(argument)
    return exempt


def loaded_names(tree: ast.Module) -> set[str]:
    """Every name *read* in the module — as a call, and as a bare value.

    Walking `Call` nodes is too narrow, and misses the one float path that
    actually threatens the serializer: `json.dumps(default=float)` passes the
    builtin as a **value**, so there is no `Call` node named `float` anywhere in
    that expression. Same reasoning for `hash`.

    **What this does not catch**, stated so the guard is not trusted for more
    than it delivers: `getattr(builtins, "float")`, a float arriving through a
    variable or a parameter, `__import__("datetime")`, or anything reached by
    `eval`. It catches the regression that matters — someone reaching for the
    obvious repair — not a determined circumvention.
    """
    exempt = _exempt_nodes(tree)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node not in exempt
    }


def attribute_names(tree: ast.Module) -> set[str]:
    """Every attribute *touched*, called or not.

    `os.environ` is a read rather than a call, and `default=datetime.now` hands
    the clock over without calling it — an `ast.Attribute` node covers both,
    where a `Call`-node walk covers neither. Receiver-blind on purpose: matching
    `os.getcwd` but not `getcwd` on some alias would be a guard with a one-line
    bypass.
    """
    return {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }


def imported_roots(tree: ast.Module) -> set[str]:
    """The top-level package of every import, from import nodes only."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def set_iterations(tree: ast.Module) -> list[str]:
    """Places that iterate a set *directly*, which is hash-ordered.

    Only the unambiguous shapes: `for x in {...}` / `for x in set(...)` and the
    same inside a comprehension. `sorted(set(...))` is fine and is not flagged,
    because the iteration order of the set never reaches the output.
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

    A guard is only worth having if it fires on the thing it forbids and stays
    silent on the thing it does not. The synthetic modules below pin both
    halves, so neither can rot: the negative control is a module whose *prose*
    is full of the forbidden words, which is exactly the shape that broke the
    `grep` this replaced.
    """

    POSITIVE = '''\
"""A module that really does the forbidden things."""
import datetime
from random import shuffle
import os
import time


def go(raw, claims, case):
    when = datetime.datetime.now()
    stamp = time.monotonic()
    here = os.getcwd()
    for c in set(claims):
        print(float(raw), hash(c), id(c), os.environ.get("HOME"))
    shuffle(claims)
    return when, stamp, here
'''

    #: The case a `Call`-node walk misses entirely, and the one that matters
    #: most: the builtin handed over as a *value*. Nothing here calls `float`
    #: or `datetime.now` — the encoder will, on the first `Decimal` it meets.
    PASSED_AS_A_VALUE = '''\
import json


def dump(document):
    return json.dumps(document, default=float, cls=None)
'''

    #: `id()` is `hash()`'s twin: an address, stable inside one process and
    #: different in the next. Both shapes are here, because the value form is
    #: the one a `Call`-node walk misses — `sort(key=id)` names no call to `id`
    #: at all.
    IDENTITY_AS_A_VALUE = '''\
def fingerprint(claims):
    return sorted(claims, key=id), [id(claim) for claim in claims]
'''

    #: The correct code the guard must leave alone: `case_id` as a *record
    #: field*, which is what `case.py` and `store.py` read on every case they
    #: touch. `id` is forbidden as a *name* and deliberately absent from
    #: FORBIDDEN_ATTRIBUTES; the attribute this layer actually reads is the
    #: `case_id`/`run_id` pair, and nothing here is named `id`.
    IDENTITY_AS_A_FIELD = '''\
def rows(case):
    return (case.case_id, case.run_id, case.paper_hash)
'''

    NEGATIVE = '''\
"""Why this module never calls float(0.1) or hash(x).

`float("0.1") + float("0.2") != 0.3`, and `hash()` varies with PYTHONHASHSEED,
so neither may decide anything here. It also reads no environment: os.environ,
getcwd() and datetime.now() are all out, and `import random` would be too.
"""

FORBIDDEN = ("float(", "hash(", "os.getcwd()", "datetime.now()", "import uuid")


def check(value: int | str | float) -> float | None:
    # A type check that *rejects* a float is the opposite of a float hazard.
    if isinstance(value, float):
        raise TypeError("no floats: see " + FORBIDDEN[0])
    return sorted({value})[0]
'''

    def test_it_fires_on_a_module_that_does_the_forbidden_things(self) -> None:
        tree = ast.parse(self.POSITIVE)
        assert {"float", "hash", "id", "shuffle"} <= loaded_names(tree)
        assert {"now", "monotonic", "getcwd", "environ"} <= attribute_names(tree)
        assert {"datetime", "random", "os", "time"} <= imported_roots(tree)
        assert set_iterations(tree)

    def test_it_fires_on_a_builtin_passed_as_a_value(self) -> None:
        # `json.dumps(default=float)` contains no Call node named `float`, so
        # the Call-only guard this replaced would have let it through — while
        # it is the one float path that actually reaches serialized output.
        tree = ast.parse(self.PASSED_AS_A_VALUE)
        assert "float" not in {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "float" in loaded_names(tree)

    def test_it_fires_on_a_bare_id_load(self) -> None:
        # `id()` returns a memory address: stable within one process, different
        # in the next — the same hazard class as `hash()`, which is already
        # forbidden. Asserted against FORBIDDEN_NAMES rather than against
        # `loaded_names` alone, because the collector has always *seen* `id`;
        # what is being pinned is that the guard now *rejects* it.
        tree = ast.parse(self.IDENTITY_AS_A_VALUE)
        assert "id" in loaded_names(tree) & FORBIDDEN_NAMES
        # And the value form specifically, which a Call-only walk cannot see:
        # `key=id` is the shape that would quietly order a whole document by
        # address.
        key_only = ast.parse("s = sorted(claims, key=id)\n")
        assert "id" not in {
            node.func.id
            for node in ast.walk(key_only)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "id" in loaded_names(key_only) & FORBIDDEN_NAMES

    def test_it_stays_silent_on_id_as_a_record_field(self) -> None:
        # `case.case_id` and `case.run_id` are legitimate fields this package
        # reads constantly. `id` is therefore forbidden as a *name* and
        # deliberately absent from FORBIDDEN_ATTRIBUTES; adding it there would
        # fire the guard on correct code, which is the spurious failure that
        # gets guards disabled — after which they never fire when it matters.
        # This test exists to stop that edit.
        tree = ast.parse(self.IDENTITY_AS_A_FIELD)
        assert "case_id" in attribute_names(tree)
        assert not (attribute_names(tree) & FORBIDDEN_ATTRIBUTES)
        assert not (loaded_names(tree) & FORBIDDEN_NAMES)

    def test_it_stays_silent_on_prose_about_the_forbidden_things(self) -> None:
        # The case the `grep` guard the plan specified gets wrong: every
        # forbidden token appears in this module as text, and none of it is
        # code.
        assert 'float("0.1")' in self.NEGATIVE
        assert "import uuid" in self.NEGATIVE
        tree = ast.parse(self.NEGATIVE)
        assert not (loaded_names(tree) & FORBIDDEN_NAMES)
        assert not (attribute_names(tree) & FORBIDDEN_ATTRIBUTES)
        assert not (imported_roots(tree) & FORBIDDEN_IMPORTS)
        assert set_iterations(tree) == []

    def test_it_stays_silent_on_an_annotation(self) -> None:
        # `x: int | str | float` names a type; it converts nothing. A token
        # scan cannot tell this from a conversion, which is the second class of
        # spurious fire — and the reason this is AST rather than tokens.
        tree = ast.parse("def f(x: float) -> float | None:\n    return None\n")
        assert "float" not in loaded_names(tree)

    def test_it_stays_silent_on_a_type_check_that_rejects_floats(self) -> None:
        # Every record in this layer rejects bad types exactly this way. A
        # guard that fired here would fire on the code enforcing the rule, and
        # be disabled.
        tree = ast.parse(
            "def f(v):\n"
            "    if isinstance(v, float):\n"
            '        raise TypeError("no floats")\n'
        )
        assert "float" not in loaded_names(tree)

    def test_sorted_around_a_set_is_not_flagged(self) -> None:
        # `sorted(set(...))` is deterministic; flagging it would be the
        # spurious failure that gets the guard disabled.
        tree = ast.parse("for x in sorted(set(y)):\n    print(x)\n")
        assert set_iterations(tree) == []


#: Modules whose mere presence is a determinism hazard in this package. The
#: store's job *is* filesystem I/O, so `pathlib` and `shutil` are deliberately
#: absent here — the contract is that nothing from the machine reaches the
#: manifest bytes, which the schema pin covers. Clock, environment, randomness
#: and process sources are all out.
FORBIDDEN_IMPORTS = frozenset(
    {
        "datetime",
        "locale",
        "os",
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

#: Bare names that may not be *referenced at all* — not called, not passed,
#: not aliased. `float` is risk R2 (`docs/ROADMAP.md:57`) and `hash` varies
#: with `PYTHONHASHSEED` from one process to the next. Referencing rather than
#: calling is the dangerous form of both: `json.dumps(default=float)` never
#: calls `float` in any line of our code, and converts every `Decimal` in the
#: document.
#:
#: `id` is here and **deliberately not in FORBIDDEN_ATTRIBUTES**: as a bare
#: name it is the builtin, which returns a memory address — `hash`'s twin,
#: stable within one process and different in the next. As an *attribute* it
#: would be a record field, but this package reads `case_id`/`run_id`, never
#: `.id`, so forbidding the name is exact and nothing legitimate fires.
FORBIDDEN_NAMES = frozenset(
    {
        "choice",
        "float",
        "getcwd",
        "getenv",
        "hash",
        "id",
        "monotonic",
        "perf_counter",
        "sample",
        "shuffle",
        "uuid4",
    }
)

#: Attributes that may not be touched, called or not: `os.environ` is a plain
#: read, `default=datetime.now` hands over the clock without calling it, and
#: `Path.resolve` materializes an absolute path the manifest must never carry.
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "choice",
        "environ",
        "getcwd",
        "getenv",
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
#: denylist, because a denylist can only ever forbid the hazards someone
#: thought of; this fails on `import getpass` too. Adding a line here is a
#: deliberate, reviewable act — which is the point — and the failure message
#: says so. `hashlib` and `json` are the deterministic primitives the identity
#: and the canonical bytes are built from; `pathlib` and `shutil` are the
#: store's own filesystem I/O, which is its job, not a hazard.
ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "hashlib",
        "json",
        "pathlib",
        "plumb",
        "re",
        "shutil",
        "typing",
    }
)


class TestNoModuleInThePackageReadsAmbientState:
    """The repo-wide version of the guard `TestTheGuardItself` applies to one module.

    Every check here parses the module and inspects real nodes. Nothing matches
    on text: the package's docstrings discuss timestamps and absolute paths —
    a `grep` for `time` would fail on the very files that document the rule,
    and a guard that fires spuriously gets disabled, after which it never fires
    when it matters.
    """

    def test_the_scan_actually_covers_the_package(self) -> None:
        # Vacuity control: a guard that scans nothing passes forever.
        names = set(module_sources())
        assert {
            "__init__.py",
            "case.py",
            "causes.py",
            "store.py",
        } <= names

    def test_no_module_references_float_or_hash_even_as_a_value(self) -> None:
        # Referenced, not merely called: `json.dumps(default=float)` is the
        # float path that reaches serialized output, and it contains no call
        # to `float`.
        offenders = {
            name: sorted(loaded_names(ast.parse(source)) & FORBIDDEN_NAMES)
            for name, source in module_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}

    def test_no_module_touches_an_attribute_that_reads_ambient_state(self) -> None:
        offenders = {
            name: sorted(attribute_names(ast.parse(source)) & FORBIDDEN_ATTRIBUTES)
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
            "environment, no randomness and no process state, then add it to "
            "ALLOWED_IMPORTS in this file."
        )

    def test_no_module_iterates_a_set_directly(self) -> None:
        offenders = {
            name: set_iterations(ast.parse(source))
            for name, source in module_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}

    def test_a_forbidden_import_in_a_real_module_would_be_flagged(self) -> None:
        # Mutation check: the scan over the package is meaningful only if it
        # would catch a forbidden import added to a real module. One added line
        # beside `store.py`'s `__future__` import must fire.
        source = module_sources()["store.py"].replace(
            "from __future__ import annotations",
            "from __future__ import annotations\nimport time",
            1,
        )
        tree = ast.parse(source)
        assert imported_roots(tree) & FORBIDDEN_IMPORTS == {"time"}


@pytest.mark.parametrize("seed", FIXED_SEEDS)
def test_the_manifest_is_byte_identical_to_a_random_seed(seed: str, tmp_path: Path) -> None:
    """Each fixed seed against a genuinely randomized one, one seed per failure.

    The baseline is `random` rather than a fixed seed on purpose: comparing
    seed `0` against seed `0` would be two processes that agree because nothing
    varied.
    """
    assert run_child("manifest", hash_seed=seed, out_dir=tmp_path / f"fixed-{seed}") == (
        run_child("manifest", hash_seed="random", out_dir=tmp_path / f"random-{seed}")
    )