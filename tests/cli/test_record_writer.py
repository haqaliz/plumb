"""Live record writer: `write_record` assembles a replayable record from a live run.

Phase 2 of `docs/planning/cross-paper-coverage/bank-flag/plan_20261002.md`,
written failing first: `write_record` (`src/plumb/cli/record.py`) takes the
live spine's materials — C1 claims, the bindings bytes, the C3 trace and
capture, and the paper — and writes a record dir that replays byte-identically
through the existing chain (`read_record` → `load_bindings` → `verify_claims`
→ `cross_check`). `objects/` carries exactly `capture.locatable`: stderr's
`diagnostic_only` artifact is never copied — it may carry local paths, and
the no-local-path invariant is load-bearing — and nothing is written outside
the record dir.
"""

from __future__ import annotations

from pathlib import Path
import sys

from plumb.cli import main
from plumb.cli.record import write_record
from plumb.cli.replay import cross_check, read_record
from plumb.extract.admit import readmit
from plumb.extract.claim import Claim
from plumb.extract.hashing import hash_paper
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.serialize import parse_claims, serialize_claims
from plumb.extract.value import parse_value
from plumb.verify import Completed, load_bindings, serialize_verdicts, verify_claims

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent / "verify"))
from verify_helpers import bindings_json, run_full, writes  # noqa: E402

#: The paper the live materials are grounded in; the claim sits at its real span.
PAPER = "# Synthetic paper\n\nAUC was 0.87.\n"
#: A real PDF, for the `paper_format="pdf"` member naming.
PDF_FIXTURE = Path("fixtures/papers/PMC12780771.pdf")


def live_materials(root: Path, *, program: str | None = None):
    """One completed C3/C4 run's materials: (claim, bindings_bytes, trace, capture).

    The claim is grounded at its real span in `PAPER`, as C1 would admit it,
    and bound to `results.json`'s `/auc` — the same shape `record_helpers`
    builds, but with the raw materials returned so `write_record` can be
    exercised directly. `program` overrides the default artifact-writing
    program; the argv the trace records is the program string itself, so a
    test that puts a local path into stderr must hand it to the program
    another way (an env var), never in `program`.
    """
    normalized = normalize_text(PAPER)
    start = normalized.index("0.87")
    value = parse_value("0.87")
    assert value is not None
    claim = Claim(
        reported_value=value, units=None, metric="AUC",
        location=CharSpan(start, start + len("0.87")),
        artifact_hint=None, tolerance_hint=None,
    )
    if program is None:
        program = writes("results.json", '{"auc": 0.8712}')
    _checkout, _result, capture, trace = run_full(root, program)
    bindings_bytes = bindings_json(
        (claim, "results.json", {"kind": "json_pointer", "pointer": "/auc"})
    )
    return claim, bindings_bytes, trace, capture


def make_record(
    tmp_path: Path, claim, bindings_bytes, trace, capture, *, paper_format: str = "markdown"
) -> Path:
    """`write_record` on the synthetic paper; the record dir is `tmp_path/record`."""
    return write_record(
        tmp_path / "record", claims=[claim], bindings_bytes=bindings_bytes,
        trace=trace, capture=capture, paper_bytes=PAPER.encode(),
        paper_format=paper_format,
    )


class TestTheRecordReplays:
    """Acceptance 1: six required members; the record replays byte-identically."""

    def test_the_six_members_and_the_read_chain_succeed(self, tmp_path: Path) -> None:
        claim, bindings_bytes, trace, capture = live_materials(tmp_path)
        verdicts = verify_claims(
            [claim], load_bindings(bindings_bytes, [claim.id]), Completed(trace, capture)
        )
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        assert record == tmp_path / "record"
        assert (record / "claims.json").is_file()
        assert (record / "bindings.json").read_bytes() == bindings_bytes
        assert (record / "trace.json").is_file()
        assert (record / "verdicts.json").read_bytes() == serialize_verdicts(verdicts)
        assert (record / "objects").is_dir()
        assert (record / "paper.md").read_bytes() == PAPER.encode()
        claims, bindings, trace2, capture2, paper, paper_format = read_record(record)
        assert paper_format == "markdown"
        assert paper == PAPER.encode()
        rederived = verify_claims(
            claims, load_bindings(bindings, [c.id for c in claims]), Completed(trace2, capture2)
        )
        cross_check(record, rederived)
        assert rederived.verdicts[0].verdict == "REPRODUCED"

    def test_the_cli_json_stdout_is_byte_identical_to_the_record(
        self, tmp_path: Path, capsys
    ) -> None:
        claim, bindings_bytes, trace, capture = live_materials(tmp_path)
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        code = main(["verify", "--from-record", str(record), "--json"])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out.encode("utf-8") == (record / "verdicts.json").read_bytes()


class TestObjectsCarryLocatableArtifactsOnly:
    """Acceptance 2: `objects/` is exactly `capture.locatable`, never stderr."""

    def test_objects_are_exactly_the_locatable_artifacts(self, tmp_path: Path) -> None:
        claim, bindings_bytes, trace, capture = live_materials(
            tmp_path,
            program="import sys\nsys.stderr.write('diagnostic: /tmp/leak')\n"
            + writes("results.json", '{"auc": 0.8712}'),
        )
        stderr_artifact = next(a for a in capture.artifacts if a.diagnostic_only)
        assert stderr_artifact.kind == "stderr"
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        names = {p.name for p in (record / "objects").iterdir()}
        assert names == {a.sha256 for a in capture.locatable}
        assert stderr_artifact.sha256 not in names
        assert (capture.store / stderr_artifact.sha256).is_file()

    def test_no_local_path_appears_in_any_record_byte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PLUMB_TEST_LEAK", str(tmp_path))
        claim, bindings_bytes, trace, capture = live_materials(
            tmp_path,
            program="import os, sys\nsys.stderr.buffer.write("
            "os.environ['PLUMB_TEST_LEAK'].encode())\n"
            + writes("results.json", '{"auc": 0.8712}'),
        )
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        leaked = [
            path for path in record.rglob("*")
            if path.is_file() and str(tmp_path).encode() in path.read_bytes()
        ]
        assert leaked == []


class TestClaimsJsonIsTheC1Form:
    """Acceptance 3: `claims.json` is the serialized C1 form of the live claims."""

    def test_claims_json_parses_and_readmits_to_the_same_ids(self, tmp_path: Path) -> None:
        claim, bindings_bytes, trace, capture = live_materials(tmp_path)
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        assert (record / "claims.json").read_bytes() == serialize_claims(
            [claim], paper_hash=hash_paper(PAPER)
        )
        records, paper_hash = parse_claims((record / "claims.json").read_bytes())
        assert paper_hash == hash_paper(PAPER)
        re_admitted = readmit(records, normalized_text=normalize_text(PAPER))
        assert [c.id for c in re_admitted] == [claim.id]


class TestNothingIsWrittenOutsideTheRecordDir:
    """Acceptance 4: the pinned checkout and the run area are never written."""

    def test_only_the_record_dir_gains_files(self, tmp_path: Path) -> None:
        claim, bindings_bytes, trace, capture = live_materials(tmp_path)
        before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
        record_files = {p.relative_to(tmp_path) for p in record.rglob("*") if p.is_file()}
        assert after - before == record_files


class TestThePaperMemberMatchesTheFormat:
    """The paper member is named by `paper_format`: `paper.pdf` for a PDF paper."""

    def test_pdf_format_writes_paper_pdf(self, tmp_path: Path) -> None:
        from plumb.pdf import pdf_to_markdown

        claim, bindings_bytes, trace, capture = live_materials(tmp_path)
        pdf = PDF_FIXTURE.read_bytes()
        record = write_record(
            tmp_path / "record", claims=[claim], bindings_bytes=bindings_bytes,
            trace=trace, capture=capture, paper_bytes=pdf, paper_format="pdf",
        )
        assert (record / "paper.pdf").read_bytes() == pdf
        assert not (record / "paper.md").exists()
        _records, paper_hash = parse_claims((record / "claims.json").read_bytes())
        assert paper_hash == hash_paper(pdf_to_markdown(pdf))