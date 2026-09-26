#!/usr/bin/env python3
"""Run-level replay of a signed bundle, from a clean clone (signed-bundle B6, PRD B6).

What a third party runs to check that the bundle's numbers came from that code — not just
that the bundle is internally consistent (`verify_bundle` does that, offline):

1. **Verify** the bundle against the given allowed-signers file; stop if it does not verify.
2. **Clone** the manifest's source at its requested rev (`resolve_git`), and check the clone's
   tree hash and resolved commit against the signed manifest (stop: `TREE_MISMATCH`).
3. **Install the frozen environment** from `environment.txt`: a venv on the recorded Python,
   then `uv pip install --no-deps` of the exact pinned versions and of the checkout itself —
   no resolution, so nothing newer can slip in.
4. **Re-run** the trace's own argv through C3 (`run_and_capture`), in a working copy.
5. **Compare.** The fresh run id covers argv + tree hash + every locatable output's hash, so an
   equal run id means every output is byte-identical. Otherwise the differing outputs are
   listed, the verdicts are re-derived on the fresh outputs, and every claim whose outcome
   moved is reported as **`UNVERIFIED` (drift)** — never as a new `DIVERGED` (constraint #3).
   The bundle is not modified.

Networked (git clone, PyPI) and slow; never imported by tests. Run by hand:
``uv run tools/bundle_replay.py bundles/agrodesign bundles/allowed_signers plumb-bundle``.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

from plumb.bundle import verify_bundle
from plumb.bundle.verify import PAPER_MEMBERS, paper_text
from plumb.extract.admit import readmit
from plumb.extract.location import normalize_text
from plumb.extract.serialize import parse_claims
from plumb.intake import EnvBuild, resolve_git
from plumb.run import EntryPoint, parse_trace, run_and_capture
from plumb.verify import Completed, load_bindings, verify_claims

TIMEOUT_SECONDS = 1800


def frozen(environment: str) -> tuple[str, list[str]]:
    lines = [line.strip() for line in environment.splitlines()
             if line.strip() and not line.startswith("#")]
    python = lines[0].removeprefix("python==")
    return python, lines[1:]


def main() -> int:
    bundle, allowed, principal = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    report = verify_bundle(bundle, allowed_signers=allowed, principal=principal)
    if not report.ok:
        print(json.dumps({"result": "BUNDLE_INVALID", "causes": report.causes}, indent=1))
        return 1
    manifest = report.manifest
    source = manifest["source"]
    trace = parse_trace((bundle / "trace.json").read_bytes())
    python, pins = frozen((bundle / "environment.txt").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="plumb-replay-") as tmp:
        root = Path(tmp)
        checkout = resolve_git(source["location"], source["rev_requested"],
                               checkout_dir=root / "checkout")
        tree = {"scheme": checkout.tree_hash.scheme, "digest": checkout.tree_hash.digest}
        if tree != manifest["tree_hash"] or checkout.source.rev_resolved != source["rev_resolved"]:
            print(json.dumps({"result": "TREE_MISMATCH", "expected": manifest["tree_hash"],
                              "got": tree, "rev": checkout.source.rev_resolved}, indent=1))
            return 1

        venv = checkout.checkout_dir / ".venv"
        subprocess.run(["uv", "venv", "--quiet", "--python", python, str(venv)], check=True)
        py = str(venv / "bin" / "python")
        (root / "pins.txt").write_text("\n".join(pins) + "\n")
        subprocess.run(["uv", "pip", "install", "--quiet", "--python", py, "--no-deps",
                        "-r", str(root / "pins.txt")], check=True)
        subprocess.run(["uv", "pip", "install", "--quiet", "--python", py, "--no-deps",
                        str(checkout.checkout_dir)], check=True)

        entry = EntryPoint(argv=trace.argv, source=trace.entrypoint_source)
        build = EnvBuild(ok=True, policy="frozen", detail="bundle environment.txt, --no-deps")
        fresh, capture = run_and_capture(checkout, build, entry, run_dir=root / "run",
                                         timeout_seconds=TIMEOUT_SECONDS)
        result = {
            "bundle_run_id": trace.run_id,
            "fresh_run_id": fresh.run_id,
            "python": python,
            "pins": len(pins),
            "run_failure": None if fresh.failure is None else fresh.failure.cause,
        }
        if fresh.failure is None and fresh.run_id == trace.run_id:
            result["result"] = "RUN_REPLAYED"
            print(json.dumps(result, indent=1))
            return 0

        before = {a.relpath: a.sha256 for a in trace.artifacts if not a.diagnostic_only}
        after = {a.relpath: a.sha256 for a in fresh.artifacts if not a.diagnostic_only}
        result["outputs_changed"] = sorted(
            p for p in before.keys() | after.keys() if before.get(p) != after.get(p)
        )
        declared = manifest["paper"]
        paper = (bundle / PAPER_MEMBERS[declared["format"]]).read_bytes()
        records, _ = parse_claims((bundle / "claims.json").read_bytes())
        claims = readmit(records, normalized_text=normalize_text(paper_text(paper, declared["format"])))
        bindings = load_bindings((bundle / "bindings.json").read_bytes(), [c.id for c in claims])
        signed = {v.claim_id: v for v in report.verdicts.verdicts}
        rederived = verify_claims(claims, bindings, Completed(fresh, capture))
        result["drift"] = [
            {"claim_id": v.claim_id, "verdict": "UNVERIFIED", "reason": "drift",
             "signed": [signed[v.claim_id].verdict, signed[v.claim_id].located_text],
             "fresh": [v.verdict, v.located_text]}
            for v in rederived.verdicts
            if (v.verdict, v.located_text) != (signed[v.claim_id].verdict,
                                                signed[v.claim_id].located_text)
        ]
        result["result"] = "RUN_DRIFTED"
        print(json.dumps(result, indent=1))
        return 2


if __name__ == "__main__":
    sys.exit(main())
