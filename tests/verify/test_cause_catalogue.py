"""Every cause in the vocabulary is reachable through the seam (M5).

A closed vocabulary is only honest if every name in it is something the engine
actually emits: a cause nothing produces is dead documentation, and a cause
produced outside the set is refused by the record. This catalogue drives one
real run whose outputs are shaped to trip each binding- and comparison-side cause
once, unions it with the run-level causes the false-`DIVERGED` guard produces,
and asserts the union is exactly `CAUSES`. One row trips its cause through the
`notebook_cell` locator (D5: a row joins the catalogue, no name joins the
vocabulary).
"""

from __future__ import annotations

from pathlib import Path

from plumb.run.capture import CaptureCaps, capture_outputs
from plumb.run.trace import build_trace
from plumb.verify import CAUSES, UNVERIFIED, Completed, load_bindings, verify_claims
from plumb.verify import causes
from test_false_diverged_guard import assert_guard
from verify_helpers import (
    OK_BUILD,
    bindings_json,
    claim,
    entry,
    make_checkout,
    run_full,
    writes,
    writes_notebook,
)

PROGRAM = (
    "import json, pathlib\n"
    'pathlib.Path("results.json").write_text(json.dumps(\n'
    '    {"auc": 0.87, "text": "n/a", "n": 10213, "z": 0.7}\n'
    "))\n"
    + writes_notebook(
        "analysis.ipynb",
        [{"cell_type": "code", "execution_count": 1, "metadata": {},
          "outputs": [{"output_type": "stream", "name": "stdout", "text": ["0.5"]},
                      {"output_type": "display_data",
                       "data": {"text/html": ["<table><thead><tr><th>x</th></tr></thead>"
                                              "<tbody><tr><td>n/a</td></tr></tbody>"
                                              "</table>"]},
                       "metadata": {}}],
          "source": ["print(0.5)"]}],
    )
    + 'print("v = 1")\nprint("v = 2")\n'
)


def ptr(p: str) -> dict:
    return {"kind": "json_pointer", "pointer": p}


#: expected cause → (claim, binding target, locator, extra binding fields); None = unbound
CASES = {
    causes.NO_BINDING: (claim("0.1", "unbound"), None),
    causes.AMBIGUOUS_BINDING: (
        claim("1", "v"), ("<stdout>", {"kind": "stdout_regex", "pattern": r"v = (\S+)"}),
    ),
    causes.BINDING_INVALID: (claim("0.87", "bad pointer"), ("results.json", ptr("auc"))),
    causes.UNPARSEABLE_VALUE: (
        claim("0.5", "cell table text"),
        ("analysis.ipynb#cell-0",
         {"kind": "notebook_cell", "pointer": "/1/data/text/html",
          "table": {"row": 0, "column": 0}}),
    ),
    causes.STALE_ARTIFACT: (claim("0.5", "old"), ("old.json", ptr("/auc"))),
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


def _cap_causes(tmp_path: Path) -> set[str]:
    """The two evidence-cap causes, each through a real run and its verdict."""
    from plumb.run.runner import run_entrypoint

    scenarios = (
        (causes.ARTIFACT_TOO_LARGE, writes("results.json", "x" * 200),
         CaptureCaps(max_artifact_bytes=10)),
        (causes.CAPTURE_LIMIT_EXCEEDED,
         writes("a.json", '{"v": 1}') + writes("b.json", '{"v": 2}'),
         CaptureCaps(max_artifact_bytes=1000, max_total_bytes=12)),
    )
    seen = set()
    for index, (expected, program, caps) in enumerate(scenarios):
        root = tmp_path / f"cap{index}"
        checkout = make_checkout(root / "proj")
        result = run_entrypoint(
            checkout, OK_BUILD, entry(program), run_dir=root / "run"
        )
        capture = capture_outputs(result, caps=caps)
        trace = build_trace(checkout, result, capture)
        assert expected in trace.causes, expected
        one = claim("0.87")
        bindings = load_bindings(
            bindings_json((one, "results.json", ptr("/auc"))), [one.id]
        )
        (verdict,) = verify_claims([one], bindings, Completed(trace, capture)).verdicts
        assert (verdict.verdict, verdict.cause) == (UNVERIFIED, expected), expected
        seen.add(expected)
    return seen


def test_the_vocabulary_is_exactly_what_the_engine_emits(tmp_path: Path) -> None:
    assert set(CASES) | assert_guard(tmp_path / "guard") | _cap_causes(tmp_path / "caps") == CAUSES
