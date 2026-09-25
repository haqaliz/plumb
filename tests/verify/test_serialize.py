"""The verdict set, serialized: the same verdicts in, the same bytes out (M7, S1).

The bytes are what C6 will bundle and a third party will replay, so they must be
identical across processes and hash seeds, carry every `Decimal` as its exact
text, and hold nothing from the user's machine — no absolute path, no clock.
The coverage summary is derived from the records at serialization time, never
tracked alongside them.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

import pytest

from plumb.verify import Completed, load_bindings, verify_claims
from plumb.verify.bindings import CsvCell, JsonPointer, StdoutRegex
from plumb.verify.compare import DIVERGED, REPRODUCED, UNVERIFIED, WITHIN_TOLERANCE
from plumb.verify.serialize import serialize_verdicts
from plumb.verify.verdict import Verdict, VerdictSet
from plumb.verify import causes
from verify_helpers import bindings_json, claim, run_full, writes

D = Decimal

_BUILD = '''
from decimal import Decimal as D
from plumb.verify.bindings import CsvCell, JsonPointer, StdoutRegex
from plumb.verify.verdict import Verdict, VerdictSet

def build():
    common = dict(reported_text="0.870", artifact="results.json", located_text="0.8700",
                  sha256="ab" * 32, run_id="cd" * 32, threshold=None, tolerance_threshold=None)
    return VerdictSet(run_id="cd" * 32, verdicts=(
        Verdict(claim_id="a", verdict="REPRODUCED", cause=None, locator=JsonPointer("/m/auc"),
                rederived=D("0.8700"), band=(D("0.8695"), D("0.8705")), tolerance_band=None,
                delta=D("0.0000"), **common),
        Verdict(claim_id="b", verdict="WITHIN-TOLERANCE", cause=None,
                locator=CsvCell("auc", (("model", "A"),)), rederived=D("1.5E+3"),
                band=(D("0.8695"), D("0.8705")), tolerance_band=(D("0.82"), D("0.92")),
                delta=D("-1E-7"), **common),
        Verdict(claim_id="c", verdict="UNVERIFIED", cause="NO_BINDING", reported_text="p < 0.001",
                artifact="<stdout>", locator=StdoutRegex(r"p = (\\S+)"), located_text=None,
                sha256=None, run_id="cd" * 32, rederived=None, band=None, tolerance_band=None,
                threshold=None, tolerance_threshold=None, delta=None),
    ))
'''
exec(_BUILD)  # defines build() here too, so in-process and child bytes are compared


def test_the_document_shape() -> None:
    document = json.loads(serialize_verdicts(build()))  # noqa: F821
    assert set(document) == {"run_id", "verdicts", "coverage"}
    first, second, third = document["verdicts"]
    assert first["locator"] == {"kind": "json_pointer", "pointer": "/m/auc"}
    assert second["locator"] == {"kind": "csv_cell", "column": "auc", "row": {"model": "A"}}
    assert third["locator"] == {"kind": "stdout_regex", "pattern": r"p = (\S+)"}
    assert first["band"] == ["0.8695", "0.8705"]
    assert first["rederived"] == "0.8700" and first["delta"] == "0.0000"
    assert second["rederived"] == "1.5E+3" and second["delta"] == "-1E-7"
    assert first["review_required"] is False and first["bound"] is True
    assert third["cause"] == "NO_BINDING" and third["bound"] is False
    assert document["coverage"] == {
        "claims": 3, "bound": 2,
        "by_verdict": {REPRODUCED: 1, WITHIN_TOLERANCE: 1, DIVERGED: 0, UNVERIFIED: 1},
        "by_cause": {"NO_BINDING": 1},
    }


def test_the_bytes_are_canonical() -> None:
    data = serialize_verdicts(build())  # noqa: F821
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    document = json.loads(data)
    assert data == (json.dumps(document, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")) + "\n").encode()


@pytest.mark.parametrize("seed", ["0", "1", "4242"])
def test_the_bytes_are_identical_across_processes(seed: str) -> None:
    child = _BUILD + (
        "\nimport sys\nfrom plumb.verify.serialize import serialize_verdicts\n"
        "sys.stdout.buffer.write(serialize_verdicts(build()))\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run([sys.executable, "-c", child], env=env, capture_output=True,
                         check=True, timeout=120).stdout
    assert out == serialize_verdicts(build())  # noqa: F821


def test_a_float_smuggled_past_the_record_is_refused() -> None:
    verdict_set = build()  # noqa: F821
    object.__setattr__(verdict_set.verdicts[0], "delta", 0.0)
    with pytest.raises(TypeError):
        serialize_verdicts(verdict_set)


def test_a_real_run_leaves_no_machine_state_in_the_bytes(tmp_path: Path) -> None:
    paper = claim("0.87")
    _, result, capture, trace = run_full(tmp_path, writes("results.json", '{"auc": 0.8712}'))
    bindings = load_bindings(
        bindings_json((paper, "results.json", {"kind": "json_pointer", "pointer": "/auc"})),
        [paper.id],
    )
    data = serialize_verdicts(verify_claims([paper], bindings, Completed(trace, capture)))
    text = data.decode()
    assert str(tmp_path) not in text and str(result.run_dir) not in text
    assert str(trace.started_at_ns) not in text
    assert json.loads(data)["verdicts"][0]["verdict"] == REPRODUCED


def test_an_empty_set_serializes() -> None:
    document = json.loads(serialize_verdicts(VerdictSet(run_id=None, verdicts=())))
    assert document["verdicts"] == [] and document["run_id"] is None
    assert document["coverage"]["claims"] == 0
