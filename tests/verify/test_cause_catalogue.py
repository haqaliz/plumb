"""Every cause in the vocabulary is reachable through the seam (M5).

A closed vocabulary is only honest if every name in it is something the engine
actually emits: a cause nothing produces is dead documentation, and a cause
produced outside the set is refused by the record. This catalogue drives one
real run whose outputs are shaped to trip each binding- and comparison-side cause
once, unions it with the run-level causes the false-`DIVERGED` guard produces,
and asserts the union is exactly `CAUSES`.
"""

from __future__ import annotations

from pathlib import Path

from plumb.verify import CAUSES, UNVERIFIED, Completed, load_bindings, verify_claims
from plumb.verify import causes
from test_false_diverged_guard import assert_guard
from verify_helpers import bindings_json, claim, run_full

PROGRAM = """\
import json, pathlib
pathlib.Path("results.json").write_text(json.dumps(
    {"auc": 0.87, "text": "n/a", "n": 10213, "z": 0.7}
))
print("v = 1")
print("v = 2")
"""


def ptr(p: str) -> dict:
    return {"kind": "json_pointer", "pointer": p}


#: expected cause → (claim, binding target, locator, extra binding fields); None = unbound
CASES = {
    causes.NO_BINDING: (claim("0.1", "unbound"), None),
    causes.AMBIGUOUS_BINDING: (
        claim("1", "v"), ("<stdout>", {"kind": "stdout_regex", "pattern": r"v = (\S+)"}),
    ),
    causes.BINDING_INVALID: (claim("0.87", "bad pointer"), ("results.json", ptr("auc"))),
    causes.UNPARSEABLE_VALUE: (claim("0.5", "text"), ("results.json", ptr("/text"))),
    causes.STALE_ARTIFACT: (claim("0.5", "old"), ("old.json", ptr("/auc"))),
    causes.UNSUPPORTED_VALUE_KIND: (claim("0.85 ± 0.03", "pm"), ("results.json", ptr("/auc"))),
    causes.UNIT_UNDECLARED: (claim("87%", "pct"), ("results.json", ptr("/auc"))),
    causes.PRECISION_AMBIGUOUS: (claim("10,000", "n"), ("results.json", ptr("/n"))),
    causes.ARTIFACT_PRECISION_COARSER: (claim("0.8712", "fine"), ("results.json", ptr("/auc"))),
    causes.NO_TOLERANCE: (
        claim("0", "zero"), ("results.json", ptr("/z"), {"tolerance": {"rel": "0.1"}}),
    ),
}


def test_each_binding_and_comparison_cause_is_emitted(tmp_path: Path) -> None:
    _, _, capture, trace = run_full(tmp_path, PROGRAM, files={"old.json": b'{"auc": 0.5}'})
    claims = [c for c, _ in CASES.values()]
    entries = [(c, *target) for c, target in CASES.values() if target is not None]
    bindings = load_bindings(bindings_json(*entries), [c.id for c in claims])
    verdicts = {v.claim_id: v for v in verify_claims(claims, bindings, Completed(trace, capture)).verdicts}
    for expected, (c, _) in CASES.items():
        assert (verdicts[c.id].verdict, verdicts[c.id].cause) == (UNVERIFIED, expected), expected


def test_the_vocabulary_is_exactly_what_the_engine_emits(tmp_path: Path) -> None:
    assert set(CASES) | assert_guard(tmp_path / "guard") == CAUSES
