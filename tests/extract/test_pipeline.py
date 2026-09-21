"""The end-to-end seam: candidates -> selection -> gate -> claims + rejections.

`extract_claims` is what C4 and `plumb verify` will consume: the deterministic
spine that turns a paper into the claims it makes and the named reasons it does
not. No verdict vocabulary appears anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

from plumb.extract.admit import NON_CLAIM_CAUSES
from plumb.extract.claim import Claim
from plumb.extract.pipeline import extract_claims
from plumb.extract.selection import SELECTION_CAUSES, SelectionRejection

PAPER = """## Abstract
The sensitivity was 0.87 and the specificity 0.92.
## References
1. Smith J. A study of things.
"""

FIXTURES = Path("fixtures/papers")


def fixture_papers() -> list[str]:
    return sorted(str(p) for p in FIXTURES.glob("*.md"))


class TestTheSeam:
    def test_claims_and_rejections_come_back_typed(self) -> None:
        claims, rejected = extract_claims(PAPER)
        assert all(isinstance(c, Claim) for c in claims)
        assert all(isinstance(r, SelectionRejection) for r in rejected)

    def test_a_real_claim_is_extracted_with_its_metric(self) -> None:
        claims, _ = extract_claims(PAPER)
        metrics = {c.metric for c in claims}
        assert "sensitivity" in metrics
        assert "specificity" in metrics

    def test_a_reference_list_number_never_reaches_the_gate(self) -> None:
        _, rejected = extract_claims(PAPER)
        causes = {r.cause for r in rejected}
        assert "reference_numeral" in causes

    def test_every_rejection_carries_a_known_cause(self) -> None:
        _, rejected = extract_claims(PAPER)
        for r in rejected:
            assert r.cause in SELECTION_CAUSES or r.cause in NON_CLAIM_CAUSES


class TestTheFixturePapers:
    def test_every_fixture_paper_runs_end_to_end(self) -> None:
        for path in fixture_papers():
            claims, rejected = extract_claims(Path(path).read_text(encoding="utf-8"))
            assert claims or rejected, f"{path} produced nothing"

    def test_extraction_is_byte_identical_across_runs(self) -> None:
        for path in fixture_papers():
            text = Path(path).read_text(encoding="utf-8")
            first = extract_claims(text)
            second = extract_claims(text)
            assert first == second, f"{path} is not deterministic"

    def test_every_claim_round_trips_and_carries_a_metric(self) -> None:
        for path in fixture_papers():
            text = Path(path).read_text(encoding="utf-8")
            claims, _ = extract_claims(text)
            for claim in claims:
                assert claim.metric, f"{path}: claim without a metric: {claim}"
                location = claim.location
                quoted = text[location.start:location.end]
                assert quoted == claim.reported_value.text, (
                    f"{path}: span does not round-trip {claim!r}"
                )

    def test_sample_sizes_never_become_claims(self) -> None:
        for path in fixture_papers():
            text = Path(path).read_text(encoding="utf-8")
            claims, _ = extract_claims(text)
            for claim in claims:
                assert claim.metric.lower() != "n", (
                    f"{path}: N reached the claim set: {claim!r}"
                )

    def test_the_abstract_claims_of_the_prevalence_paper_are_found(self) -> None:
        text = Path("fixtures/papers/PMC13134363.md").read_text(encoding="utf-8")
        claims, _ = extract_claims(text)
        values = {c.reported_value.text for c in claims}
        assert "0.8" in values  # the pooled prevalence the paper headlines