"""`plumb verify --proposer CMD` end to end (issue #24).

The proposer is a user command; these tests run a local stub. Nothing here needs a model, a
network or a key — and the accepted bindings are what a bundle carries, so the replay does not
need the proposer either.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from plumb.bundle import verify_bundle
from plumb.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
PAPER = FIXTURES / "paper.md"
REPO = FIXTURES / "repo"
ACCURACY_ID = "b3b87b2b43490a529cf2ad7662321e46c3b916aaa0ca6ab74f887d31db2b8000"
PRECISION_ID = "3e137a2e267b131b53702683f7e6f2a85625377ddd67a3dcc6d8d3edc1721de5"

GOOD = {"bindings": [
    {"claim_id": ACCURACY_ID, "artifact": "results.json",
     "locator": {"kind": "json_pointer", "pointer": "/metrics/accuracy"}, "float_repr": True},
    {"claim_id": PRECISION_ID, "artifact": "results.json",
     "locator": {"kind": "json_pointer", "pointer": "/metrics/precision"}, "float_repr": True},
]}


def argv(*extra: str) -> list[str]:
    return ["verify", str(PAPER), str(REPO), "--no-env-build", *extra]


def stub(tmp_path: Path, document: dict | None, *, exit_code: int = 0) -> str:
    """A proposer command: echo `document`, and keep its request for inspection."""
    script = tmp_path / f"stub-{exit_code}-{len(list(tmp_path.iterdir()))}.py"
    lines = [
        "import json, sys",
        "request = sys.stdin.read()",
        f"open({str(tmp_path / 'request.json')!r}, 'w', encoding='utf-8').write(request)",
    ]
    if exit_code:
        lines.append(f"sys.exit({exit_code})")
    else:
        lines.append(f"print({json.dumps(json.dumps(document))})")
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def make_key(directory: Path) -> Path:
    directory.mkdir()
    key = directory / "signer"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "plumb-bundle", "-f", str(key)],
        check=True, capture_output=True,
    )
    (directory / "allowed_signers").write_text(
        f"plumb-bundle {(directory / 'signer.pub').read_text().strip()}\n", encoding="utf-8"
    )
    return key


class TestArgumentRules:
    def test_bindings_and_proposer_together_are_a_usage_error(self, tmp_path: Path, capsys) -> None:
        code = main(argv("--bindings", str(FIXTURES / "bindings.json"),
                         "--proposer", stub(tmp_path, GOOD)))
        assert code == 2
        assert "exactly one" in capsys.readouterr().err

    def test_neither_is_a_usage_error(self, capsys) -> None:
        assert main(argv()) == 2
        assert "--bindings FILE or --proposer CMD is required" in capsys.readouterr().err

    def test_from_record_rejects_a_proposer(self, capsys) -> None:
        code = main(["verify", "--from-record", "nope", "--proposer", "true"])
        err = capsys.readouterr().err
        assert code == 2
        assert "--proposer" in err


class TestProposedBindings:
    def test_a_grounded_proposal_verifies(self, tmp_path: Path, capsys) -> None:
        code = main(argv("--proposer", stub(tmp_path, GOOD)))
        out = capsys.readouterr().out
        assert code == 0
        assert "REPRODUCED: 2" in out

    def test_the_proposer_sees_claims_and_artifacts_not_the_paper(
        self, tmp_path: Path, capsys
    ) -> None:
        main(argv("--proposer", stub(tmp_path, GOOD)))
        request = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
        assert [c["metric"] for c in request["claims"]] == ["accuracy", "precision"]
        assert "results.json" in [a["relpath"] for a in request["artifacts"]]
        assert "paper" not in request

    def test_an_ungrounded_proposal_is_refused_and_never_decided(
        self, tmp_path: Path, capsys
    ) -> None:
        document = {"bindings": [GOOD["bindings"][0], {
            "claim_id": PRECISION_ID, "artifact": "results.json",
            "locator": {"kind": "json_pointer", "pointer": "/metrics/nope"},
        }]}
        code = main(argv("--proposer", stub(tmp_path, document)))
        captured = capsys.readouterr()
        assert code == 1
        assert "REPRODUCED: 1" in captured.out
        assert "UNVERIFIED: 1" in captured.out
        assert "MODEL_ONLY_SIGNAL" in captured.err

    def test_a_failing_proposer_is_a_named_cause(self, tmp_path: Path, capsys) -> None:
        code = main(argv("--proposer", stub(tmp_path, None, exit_code=3)))
        captured = capsys.readouterr()
        assert code == 1
        assert "PROPOSER_FAILED" in captured.err
        assert "Traceback" not in captured.err

    def test_the_bundle_carries_the_accepted_bindings(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        key = make_key(tmp_path / "keys")
        out = tmp_path / "bundle"
        # A local absolute path in the manifest is refused by design; relative + chdir.
        root = Path(__file__).resolve().parents[2]
        monkeypatch.chdir(root)
        code = main([
            "verify", os.path.relpath(PAPER, root), os.path.relpath(REPO, root),
            "--no-env-build", "--proposer", stub(tmp_path, GOOD),
            "--out", str(out), "--signer-key", str(key),
        ])
        assert code == 0, capsys.readouterr()
        report = verify_bundle(
            out, allowed_signers=tmp_path / "keys" / "allowed_signers", principal="plumb-bundle"
        )
        assert report.ok, report.causes
        carried = json.loads((out / "bindings.json").read_text(encoding="utf-8"))
        assert {item["claim_id"] for item in carried["bindings"]} == {ACCURACY_ID, PRECISION_ID}
