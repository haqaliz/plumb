"""C4 end to end: intake → run → bind → verdict, on a synthetic local repo (S2).

The first place Plumb emits verdicts over a real run. A small repo's `main.py`
writes a JSON result, a CSV table and a line of stdout; it also carries a
committed, back-dated result the run never touches. C2 resolves it, C3 runs the
discovered entry point and captures, and C4 verifies five hand-built claims —
one of each outcome the gate cares about. Offline: the program is local, the
env build is a stub.

This proves the spine joins end to end. It is **not** the Phase 0 gate: no real
paper's repo is run here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import plumb.intake as intake
import plumb.run as run
from plumb.verify import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    WITHIN_TOLERANCE,
    Completed,
    load_bindings,
    serialize_verdicts,
    verify_claims,
)
from plumb.verify import causes
from verify_helpers import OLD, bindings_json, claim

MAIN = b"""\
import csv, json
json.dump({"metrics": {"auc": 0.8712, "f1": 0.91}}, open("results.json", "w"))
with open("table.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["model", "accuracy"])
    w.writerow(["ours", "0.842"])
print("p = 0.0004")
"""

AUC = claim("0.87", "AUC")  # 0.8712 is inside 0.87's written precision
ACC = claim("85.0%", "accuracy")  # table.csv's 0.842 at scale 100 is 84.2: within ±1
F1 = claim("0.87", "F1")  # the run wrote 0.91
OLD_AUC = claim("0.80", "AUC (committed)")  # bound to the committed file
P = claim("p < 0.001", "p-value")  # left unbound


def test_one_of_each_verdict_through_the_whole_spine(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    (repo / "committed").mkdir(parents=True)
    (repo / "main.py").write_bytes(MAIN)
    (repo / "committed" / "results.json").write_bytes(b'{"auc": 0.80}')
    os.utime(repo / "committed" / "results.json", (OLD, OLD))

    checkout = intake.resolve_local(repo)
    descriptor = intake.describe_environment(checkout, tool_versions={})
    build = intake.build_environment(
        checkout, descriptor,
        runner=lambda c, d: intake.EnvBuild(ok=True, policy=d.policy, detail="stub"),
    )
    discovered = run.resolve_entrypoint(checkout, descriptor.manifests)
    entry = run.EntryPoint(argv=(sys.executable, "main.py"), source=discovered.source)
    trace, capture = run.run_and_capture(checkout, build, entry, run_dir=tmp_path / "run")

    claims = [AUC, ACC, F1, OLD_AUC, P]
    bindings = load_bindings(
        bindings_json(
            (AUC, "results.json", {"kind": "json_pointer", "pointer": "/metrics/auc"}),
            (ACC, "table.csv",
             {"kind": "csv_cell", "column": "accuracy", "row": {"model": "ours"}},
             {"scale": "100", "tolerance": {"abs": "1"}}),
            (F1, "results.json", {"kind": "json_pointer", "pointer": "/metrics/f1"}),
            (OLD_AUC, "committed/results.json", {"kind": "json_pointer", "pointer": "/auc"}),
        ),
        [c.id for c in claims],
    )
    result = verify_claims(claims, bindings, Completed(trace, capture))
    verdicts = {v.claim_id: v for v in result.verdicts}

    assert verdicts[AUC.id].verdict == REPRODUCED
    assert verdicts[ACC.id].verdict == WITHIN_TOLERANCE
    assert verdicts[F1.id].verdict == DIVERGED and verdicts[F1.id].review_required
    assert (verdicts[OLD_AUC.id].verdict, verdicts[OLD_AUC.id].cause) == (
        UNVERIFIED, causes.STALE_ARTIFACT,
    )
    assert (verdicts[P.id].verdict, verdicts[P.id].cause) == (UNVERIFIED, causes.NO_BINDING)

    document = json.loads(serialize_verdicts(result))
    assert document["run_id"] == trace.run_id
    assert document["coverage"]["claims"] == 5
    assert document["coverage"]["bound"] == 3
    assert document["coverage"]["by_verdict"] == {
        REPRODUCED: 1, WITHIN_TOLERANCE: 1, DIVERGED: 1, UNVERIFIED: 2,
    }
