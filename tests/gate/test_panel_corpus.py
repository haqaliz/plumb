"""The panel's pooled R1 figure, pinned against the two real fixtures.

Banks `fixtures/gate/agrodesign/` and `fixtures/gate/perrin/` into a temp store through
the real CLI and asserts the pooled totals the docs publish: 102 claims, 102 bound,
87 `REPRODUCED`, 15 `DIVERGED`, 0 `UNVERIFIED`, precision/recall `1/15 (owner)` — the
owner's real cases live in the gitignored local store, so this test re-derives the
published arithmetic from the committed fixtures alone; a fixture edit can never let the
docs drift silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb.cli import main

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gate"

TOTAL_CLAIMS = 102
BY_VERDICT = {"REPRODUCED": 87, "WITHIN-TOLERANCE": 0, "DIVERGED": 15, "UNVERIFIED": 0}


def test_the_pooled_panel_figure(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    store = tmp_path / "store"
    for name in ("agrodesign", "perrin"):
        assert main(["corpus", "bank", str(FIXTURES / name), "--store", str(store)]) == 0
        capsys.readouterr()

    assert main(["corpus", "report", "--store", str(store), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)

    totals = document["totals"]
    assert document["authority"] == "owner"
    assert len(document["cases"]) == 2
    assert totals["coverage"]["claims"] == TOTAL_CLAIMS
    assert totals["coverage"]["bound"] == TOTAL_CLAIMS
    assert dict(totals["coverage"]["by_verdict"]) == BY_VERDICT
    # AgroDesign's one confirmed DIVERGED is the only confirmed flag; Perrin's 14 are
    # refuted (the artifact is not run-to-run reproducible at the written precision).
    assert totals["precision"] == {"confirmed": 1, "flagged": 15}
    assert totals["recall"] == {"confirmed": 1, "flagged": 15}
