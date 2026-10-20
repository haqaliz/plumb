"""The proposer re-grounds; a proposal alone never decides (issue #24)."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import sys

import pytest

from plumb.propose import (
    MODEL_ONLY_SIGNAL,
    PROPOSER_FAILED,
    PROPOSER_UNGROUNDED,
    ProposalRefused,
    ground,
    propose_bindings,
    request_document,
)

sys.path.insert(0, str(Path(__file__).parent.parent / "verify"))
from verify_helpers import claim, run_full, writes  # noqa: E402

POINTER = {"kind": "json_pointer", "pointer": "/auc"}


def captured(tmp_path: Path):
    _, _, capture, _trace = run_full(tmp_path, writes("results.json", '{"auc": 0.87}'))
    return claim("0.87"), capture


def proposals(*entries) -> bytes:
    return json.dumps({"bindings": list(entries)}).encode()


class TestGrounding:
    def test_a_real_locator_is_accepted(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        entry = {"claim_id": one.id, "artifact": "results.json", "locator": POINTER}
        accepted, refusals = ground(proposals(entry), [one], capture)
        assert refusals == ()
        assert json.loads(accepted) == {"bindings": [entry]}

    def test_an_unknown_claim_is_refused(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        entry = {"claim_id": "0" * 64, "artifact": "results.json", "locator": POINTER}
        _, refusals = ground(proposals(entry), [one], capture)
        assert [r.cause for r in refusals] == [PROPOSER_UNGROUNDED]

    def test_an_artifact_the_run_did_not_write_is_refused(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        entry = {"claim_id": one.id, "artifact": "nowhere.json", "locator": POINTER}
        _, refusals = ground(proposals(entry), [one], capture)
        assert [r.cause for r in refusals] == [PROPOSER_UNGROUNDED]

    def test_a_locator_that_finds_nothing_is_a_model_only_signal(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        entry = {"claim_id": one.id, "artifact": "results.json",
                 "locator": {"kind": "json_pointer", "pointer": "/nope"}}
        _, refusals = ground(proposals(entry), [one], capture)
        assert [r.cause for r in refusals] == [MODEL_ONLY_SIGNAL]

    def test_unknown_fields_are_refused(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        entry = {"claim_id": one.id, "artifact": "results.json", "locator": POINTER,
                 "verdict": "REPRODUCED"}
        _, refusals = ground(proposals(entry), [one], capture)
        assert [r.cause for r in refusals] == [PROPOSER_UNGROUNDED]

    def test_a_duplicate_claim_keeps_the_first_grounding(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        entry = {"claim_id": one.id, "artifact": "results.json", "locator": POINTER}
        accepted, refusals = ground(proposals(entry, entry), [one], capture)
        assert len(json.loads(accepted)["bindings"]) == 1
        assert [r.cause for r in refusals] == [PROPOSER_UNGROUNDED]

    def test_a_non_bindings_document_fails_the_proposer(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        with pytest.raises(ProposalRefused) as refused:
            ground(b'{"proposals": []}', [one], capture)
        assert refused.value.cause == PROPOSER_FAILED


class TestTheCommand:
    def test_the_request_carries_claims_and_artifact_paths_only(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        document = json.loads(request_document([one], capture))
        assert document["claims"] == [
            {"id": one.id, "metric": "AUC", "reported": "0.87", "units": None}
        ]
        assert {"relpath": "results.json", "kind": "json"} in document["artifacts"]
        assert "paper" not in document

    def test_the_command_is_run_and_grounded(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        stub = tmp_path / "stub.py"
        stub.write_text(
            "import json, sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'bindings': [{'claim_id': %r, 'artifact': 'results.json', "
            "'locator': {'kind': 'json_pointer', 'pointer': '/auc'}}]}))\n" % one.id,
            encoding="utf-8",
        )
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(stub))}"
        accepted, refusals = propose_bindings(command, [one], capture)
        assert refusals == ()
        assert json.loads(accepted)["bindings"][0]["claim_id"] == one.id

    def test_a_failing_command_is_a_named_cause(self, tmp_path: Path) -> None:
        one, capture = captured(tmp_path)
        command = f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(3)'"
        with pytest.raises(ProposalRefused) as refused:
            propose_bindings(command, [one], capture)
        assert refused.value.cause == PROPOSER_FAILED
