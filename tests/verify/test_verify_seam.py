"""`verify_claims`: one verdict per claim against one run, run causes first (M4).

The seam joins C1 and C3. It takes the claims, the bindings, and either a
completed run (`Completed(trace, capture)`) or the reason nothing ran
(`NoRun(cause)` — the causes C2/C3 raise before any trace exists). Pinned here:

- every input claim gets exactly one record, sorted by claim id — an unbound
  claim is present as `NO_BINDING`, never dropped;
- a run that failed governs every verdict, even when its outputs were captured
  and would have matched ("the run's failure governs the verdict",
  `plumb.run.capture`);
- the trace and the capture must describe the same run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.intake.causes import EnvBuildFailed
from plumb.run.causes import EntryPointAmbiguous, EntryPointMissing
from plumb.verify import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    Completed,
    NoRun,
    load_bindings,
    verify_claims,
)
from plumb.verify import causes
from plumb.verify.causes import BindingInvalid
from verify_helpers import bindings_json, claim, run_full, writes

AUC = claim("0.87", "AUC")
F1 = claim("0.91", "F1")
P = claim("p < 0.001", "p-value")
CLAIMS = (AUC, F1, P)


def ptr(p: str) -> dict:
    return {"kind": "json_pointer", "pointer": p}


def completed(tmp_path: Path, program: str, **kw) -> Completed:
    _, _, capture, trace = run_full(tmp_path, program, **kw)
    return Completed(trace, capture)


def by_id(verdict_set) -> dict:
    return {v.claim_id: v for v in verdict_set.verdicts}


class TestOnePerClaim:
    def test_every_claim_gets_exactly_one_record_sorted_by_id(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", '{"auc": 0.8712, "p": 0.0004}'))
        bindings = load_bindings(
            bindings_json((AUC, "results.json", ptr("/auc")), (P, "results.json", ptr("/p"))),
            [c.id for c in CLAIMS],
        )
        result = verify_claims(CLAIMS, bindings, run)
        assert [v.claim_id for v in result.verdicts] == sorted(c.id for c in CLAIMS)
        verdicts = by_id(result)
        assert verdicts[AUC.id].verdict == REPRODUCED
        assert verdicts[P.id].verdict == REPRODUCED
        assert (verdicts[F1.id].verdict, verdicts[F1.id].cause) == (UNVERIFIED, causes.NO_BINDING)
        assert result.run_id == run.trace.run_id

    def test_a_decided_record_carries_its_evidence(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", '{"auc": 0.8712}'))
        bindings = load_bindings(bindings_json((AUC, "results.json", ptr("/auc"))), [AUC.id])
        (verdict,) = verify_claims([AUC], bindings, run).verdicts
        artifact = next(a for a in run.capture.artifacts if a.relpath == "results.json")
        assert verdict.located_text == "0.8712"
        assert verdict.sha256 == artifact.sha256
        assert verdict.run_id == run.trace.run_id
        assert verdict.reported_text == "0.87"
        assert verdict.artifact == "results.json"

    def test_a_located_but_diverging_value_is_diverged_and_flagged(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", '{"auc": 0.95}'))
        bindings = load_bindings(bindings_json((AUC, "results.json", ptr("/auc"))), [AUC.id])
        (verdict,) = verify_claims([AUC], bindings, run).verdicts
        assert verdict.verdict == DIVERGED
        assert verdict.review_required

    def test_a_binding_side_cause_is_recorded_with_its_target(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", '{"auc": 0.87}'))
        bindings = load_bindings(bindings_json((AUC, "results.json", ptr("/f1"))), [AUC.id])
        (verdict,) = verify_claims([AUC], bindings, run).verdicts
        assert (verdict.verdict, verdict.cause) == (UNVERIFIED, causes.NO_BINDING)
        assert verdict.artifact == "results.json"
        assert verdict.locator is not None
        assert not verdict.bound

    def test_a_gated_claim_is_bound_but_unverified(self, tmp_path: Path) -> None:
        pm = claim("0.85 ± 0.03")
        run = completed(tmp_path, writes("results.json", '{"auc": 0.85}'))
        bindings = load_bindings(bindings_json((pm, "results.json", ptr("/auc"))), [pm.id])
        (verdict,) = verify_claims([pm], bindings, run).verdicts
        assert verdict.cause == causes.UNSUPPORTED_VALUE_KIND
        assert verdict.bound and verdict.located_text == "0.85"

    def test_an_empty_claim_set_is_an_empty_verdict_set(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", "{}"))
        result = verify_claims([], load_bindings(b'{"bindings": []}', []), run)
        assert result.verdicts == ()


class TestRunCausesGovern:
    def test_a_failed_run_with_a_matching_output_is_still_unverified(
        self, tmp_path: Path
    ) -> None:
        program = writes("results.json", '{"auc": 0.87}') + "raise SystemExit(3)\n"
        run = completed(tmp_path, program)
        assert run.trace.failure is not None
        assert any(a.relpath == "results.json" for a in run.capture.artifacts)
        bindings = load_bindings(bindings_json((AUC, "results.json", ptr("/auc"))), [AUC.id])
        (verdict,) = verify_claims([AUC], bindings, run).verdicts
        assert (verdict.verdict, verdict.cause) == (UNVERIFIED, causes.WONT_RUN)
        assert verdict.run_id == run.trace.run_id
        assert verdict.located_text is None

    def test_a_silent_run_is_no_artifact_for_every_claim(self, tmp_path: Path) -> None:
        run = completed(tmp_path, "pass\n")
        result = verify_claims(CLAIMS, load_bindings(b'{"bindings": []}', []), run)
        assert {(v.verdict, v.cause) for v in result.verdicts} == {
            (UNVERIFIED, causes.NO_ARTIFACT)
        }

    @pytest.mark.parametrize(
        ("exc", "cause"),
        [
            (EntryPointMissing("none"), causes.ENTRYPOINT_MISSING),
            (EntryPointAmbiguous("two"), causes.ENTRYPOINT_AMBIGUOUS),
            (EnvBuildFailed("uv sync failed"), causes.ENV_BUILD_FAILED),
        ],
    )
    def test_nothing_ran_is_unverified_for_every_claim(self, exc, cause: str) -> None:
        run = NoRun.from_exception(exc)
        assert run.cause == cause
        result = verify_claims(CLAIMS, load_bindings(b'{"bindings": []}', []), run)
        assert result.run_id is None
        assert {(v.verdict, v.cause, v.run_id) for v in result.verdicts} == {
            (UNVERIFIED, cause, None)
        }

    def test_no_run_accepts_only_the_pre_run_causes(self) -> None:
        with pytest.raises(ValueError):
            NoRun(causes.WONT_RUN)
        with pytest.raises(TypeError):
            NoRun.from_exception(RuntimeError("something else"))


class TestRefusals:
    def test_a_trace_and_capture_from_different_runs_are_refused(self, tmp_path: Path) -> None:
        a = completed(tmp_path / "a", writes("results.json", '{"auc": 0.87}'))
        b = completed(tmp_path / "b", writes("results.json", '{"auc": 0.95}'))
        with pytest.raises(ValueError, match="same run"):
            verify_claims([AUC], load_bindings(b'{"bindings": []}', []),
                          Completed(a.trace, b.capture))

    def test_duplicate_claims_are_refused(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", "{}"))
        with pytest.raises(BindingInvalid):
            verify_claims([AUC, AUC], load_bindings(b'{"bindings": []}', []), run)

    def test_a_binding_for_a_claim_not_given_is_refused(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", "{}"))
        bindings = load_bindings(bindings_json((F1, "results.json", ptr("/f1"))), [F1.id])
        with pytest.raises(BindingInvalid):
            verify_claims([AUC], bindings, run)

    def test_a_tampered_store_raises_out_of_the_seam(self, tmp_path: Path) -> None:
        run = completed(tmp_path, writes("results.json", '{"auc": 0.87}'))
        artifact = next(a for a in run.capture.artifacts if a.relpath == "results.json")
        (run.capture.store / artifact.sha256).write_bytes(b'{"auc": 0.95}')
        bindings = load_bindings(bindings_json((AUC, "results.json", ptr("/auc"))), [AUC.id])
        with pytest.raises(ValueError, match="does not match its hash"):
            verify_claims([AUC], bindings, run)


class TestThePublicSurface:
    def test_the_seam_exports(self) -> None:
        import plumb.verify as verify

        for name in ("verify_claims", "load_bindings", "serialize_verdicts", "Completed",
                     "NoRun", "Verdict", "VerdictSet", "BindingInvalid", "CAUSES"):
            assert hasattr(verify, name), name

    def test_the_docstring_documents_every_cause(self) -> None:
        import plumb.verify as verify

        doc = verify.__doc__ or ""
        for cause in verify.CAUSES:
            assert f"`{cause}`" in doc, cause


class TestFloatReprThroughTheSeam:
    """pandas writes the exact 2.5 as `2.5`; the paper's `2.500` must not look coarser."""

    MS = claim("2.500", "Residual MS")

    def _verdict(self, tmp_path: Path, **extra):
        run = completed(tmp_path, writes("t.csv", ",MS\nResidual,2.5\n"))
        locator = {"kind": "csv_cell", "column": "MS", "row": {"": "Residual"}}
        bindings = load_bindings(bindings_json((self.MS, "t.csv", locator, extra)), [self.MS.id])
        (verdict,) = verify_claims([self.MS], bindings, run).verdicts
        return verdict

    def test_without_the_flag_it_is_coarser(self, tmp_path: Path) -> None:
        assert self._verdict(tmp_path).cause == causes.ARTIFACT_PRECISION_COARSER

    def test_with_the_flag_it_is_reproduced(self, tmp_path: Path) -> None:
        assert self._verdict(tmp_path, float_repr=True).verdict == REPRODUCED
