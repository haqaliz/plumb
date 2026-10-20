"""C7 internal-consistency checks (issue #23).

The statistical core is pinned against textbook values, then the conservative rules: rounding is
never an inconsistency, an unlabeled one-sided report is never flagged, a missing df is
`NOT_APPLICABLE`, and no label is ever a `DIVERGED`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.cli import main
from plumb.consistency import (
    CONSISTENT,
    INTERNAL_INCONSISTENCY,
    NOT_APPLICABLE,
    check_consistency,
)
from plumb.consistency.distribution import (
    p_chi2,
    p_f,
    p_t_one_sided,
    p_t_two_sided,
    p_z_two_sided,
)
from plumb.consistency.grim import scan_means
from plumb.consistency.statcheck import scan_statistics


class TestTheTwoSpecialFunctions:
    """Known critical values: a wrong p would flip a verdict, so pin them."""

    @pytest.mark.parametrize(
        "value,df,expected",
        [(2.41, 28, 0.02277), (1.96, 1000, 0.05027), (0.0, 10, 1.0), (5.0, 28, 0.0000262)],
    )
    def test_two_sided_t(self, value, df, expected) -> None:
        assert p_t_two_sided(value, df) == pytest.approx(expected, abs=1e-4)

    def test_one_sided_t_is_half(self) -> None:
        assert p_t_one_sided(2.41, 28) == pytest.approx(p_t_two_sided(2.41, 28) / 2)

    @pytest.mark.parametrize(
        "value,df1,df2,expected",
        [(5.0, 1, 28, 0.03350), (1.0, 1, 28, 0.3258), (3.0, 2, 20, 0.07254)],
    )
    def test_f(self, value, df1, df2, expected) -> None:
        assert p_f(value, df1, df2) == pytest.approx(expected, abs=1e-4)

    @pytest.mark.parametrize("value,df,expected", [(3.841, 1, 0.05), (5.991, 2, 0.05)])
    def test_chi2(self, value, df, expected) -> None:
        assert p_chi2(value, df) == pytest.approx(expected, abs=1e-4)

    def test_z(self) -> None:
        assert p_z_two_sided(1.96) == pytest.approx(0.05, abs=1e-3)


class TestStatcheckIsConservative:
    def test_rounding_is_never_an_inconsistency(self) -> None:
        (finding,) = scan_statistics("t(28) = 2.41, p = .02")
        assert finding.label == CONSISTENT

    def test_a_real_mismatch_is_flagged(self) -> None:
        (finding,) = scan_statistics("t(28) = 2.41, p = .30")
        assert finding.label == INTERNAL_INCONSISTENCY
        assert "0.0227" in finding.detail

    def test_an_unlabeled_one_sided_report_is_not_flagged(self) -> None:
        (finding,) = scan_statistics("t(28) = 2.41, p = .011")
        assert finding.label == CONSISTENT

    def test_a_bound_is_checked_as_a_bound(self) -> None:
        assert scan_statistics("t(28) = 5.0, p < .001")[0].label == CONSISTENT
        assert scan_statistics("t(28) = 0.5, p < .001")[0].label == INTERNAL_INCONSISTENCY

    def test_a_missing_df_is_not_applicable(self) -> None:
        (finding,) = scan_statistics("t = 2.41, p = .02")
        assert finding.label == NOT_APPLICABLE
        assert "df" in finding.detail

    def test_r_is_converted_to_t(self) -> None:
        (finding,) = scan_statistics("r(28) = .41, p = .02")
        assert finding.label == CONSISTENT

    def test_chi2_and_f_are_one_sided(self) -> None:
        assert scan_statistics("χ2(1) = 3.84, p = .05")[0].label == CONSISTENT
        assert scan_statistics("F(1, 28) = 5.0, p = .03")[0].label == CONSISTENT
        assert scan_statistics("χ2(1) = 3.84, p = .20")[0].label == INTERNAL_INCONSISTENCY


class TestGrim:
    def test_an_unreachable_mean_is_flagged(self) -> None:
        (finding,) = scan_means("The mean was 3.72 (N = 30).")
        assert finding.label == INTERNAL_INCONSISTENCY
        assert "111.60" in finding.detail and "0.15" in finding.detail

    def test_a_reachable_mean_passes(self) -> None:
        (finding,) = scan_means("The mean was 3.70 (N = 30).")
        assert finding.label == CONSISTENT

    def test_the_rounding_boundary_is_consistent(self) -> None:
        # 149/40 = 3.725 rounds into 3.72 at two decimals: reachable, so not a finding.
        (finding,) = scan_means("The mean was 3.72 (N = 40).")
        assert finding.label == CONSISTENT

    def test_no_n_means_no_check(self) -> None:
        assert scan_means("The mean was 3.72.") == []

    def test_a_non_positive_n_is_not_applicable(self) -> None:
        (finding,) = scan_means("The mean was 3.72, N = 0.")
        assert finding.label == NOT_APPLICABLE


class TestNoLabelIsAVerdict:
    def test_the_report_never_emits_a_verdict_word(self) -> None:
        report = check_consistency(
            "t(28) = 2.41, p = .30. The mean was 3.72 (N = 30)."
        )
        labels = {f.label for f in report.findings}
        assert labels <= {INTERNAL_INCONSISTENCY, CONSISTENT, NOT_APPLICABLE}
        assert report.inconsistent
        assert report.counts()[INTERNAL_INCONSISTENCY] == 2

    def test_findings_are_in_text_order(self) -> None:
        report = check_consistency("t(28) = 2.41, p = .02. mean = 3.72, N = 40.")
        assert [f.kind for f in report.findings] == ["statcheck", "grim"]


class TestTheCli:
    def test_an_inconsistency_exits_1_and_says_it_is_not_a_verdict(
        self, tmp_path: Path, capsys
    ) -> None:
        paper = tmp_path / "paper.md"
        paper.write_text("# Results\n\nt(28) = 2.41, p = .30\n", encoding="utf-8")
        code = main(["consistency", str(paper)])
        out = capsys.readouterr().out
        assert code == 1
        assert INTERNAL_INCONSISTENCY in out
        assert "not a reproduction verdict" in out
        assert "DIVERGED" not in out

    def test_a_clean_paper_exits_0(self, tmp_path: Path, capsys) -> None:
        paper = tmp_path / "paper.md"
        paper.write_text("# Results\n\nt(28) = 2.41, p = .02\n", encoding="utf-8")
        assert main(["consistency", str(paper)]) == 0
        assert "inconsistencies: 0" in capsys.readouterr().out

    def test_json(self, tmp_path: Path, capsys) -> None:
        import json

        paper = tmp_path / "paper.md"
        paper.write_text("t(28) = 2.41, p = .02\n", encoding="utf-8")
        code = main(["consistency", str(paper), "--json"])
        document = json.loads(capsys.readouterr().out)
        assert code == 0
        assert document["counts"][CONSISTENT] == 1
        assert document["findings"][0]["kind"] == "statcheck"
        assert len(document["paper_sha256"]) == 64

    def test_a_missing_paper_is_a_named_cause(self, tmp_path: Path, capsys) -> None:
        code = main(["consistency", str(tmp_path / "nope.md")])
        captured = capsys.readouterr()
        assert code == 1
        assert "plumb consistency: PAPER_UNREADABLE" in captured.err
        assert "Traceback" not in captured.err
