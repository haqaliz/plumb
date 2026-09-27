"""render determinism: cross-process byte identity under varied `PYTHONHASHSEED`.

Acceptance 3 of `docs/planning/verify-cli/render/spec.md`: two subprocess invocations
under different `PYTHONHASHSEED` values produce identical bytes for both `--json` and
the table. In-process assertions of determinism are worthless — inside one interpreter
`dict`/`set` iteration order is stable, so they pass while the contract is broken — so
the load-bearing tests here spawn fresh interpreters and compare raw stdout **bytes**
(style of `tests/extract/test_determinism.py`).

The seed control matters as much as the identity tests: `test_the_hash_seed_really_varies`
proves the children observably disagree about `hash()` under the seeds this file uses, so
identical documents are evidence about the renderer rather than about broken plumbing.
"""

from __future__ import annotations

from pathlib import Path

from test_render import _REPO_ROOT, _THIS_DIR, replay, render_child_direct, run_child

SEEDS = ("0", "1", "12345", "random")
FIXED_SEEDS = ("0", "1", "12345")


def _probe() -> bytes:
    from test_render import probe

    return probe()


class TestTheSeedControl:
    """Proof that the seeds reach the children — without it, identity proves nothing."""

    def test_the_hash_seed_really_varies_in_the_child(self) -> None:
        probes = {seed: run_child("probe", hash_seed=seed) for seed in FIXED_SEEDS}
        distinct = set(probes.values())
        assert len(distinct) == len(FIXED_SEEDS), (
            "the children agree about hash() under different PYTHONHASHSEED values, "
            "so the seed is not reaching them and the byte-identity tests below "
            f"prove nothing: {probes}"
        )

    def test_the_child_really_is_a_separate_process(self) -> None:
        here = _probe()
        elsewhere = {run_child("probe", hash_seed=seed) for seed in FIXED_SEEDS}
        assert any(probe != here for probe in elsewhere)


class TestCrossProcessByteIdentity:
    """The same verdict set, in fresh interpreters, produces the same bytes."""

    def test_json_bytes_are_identical_across_hash_seeds(self) -> None:
        outputs = {seed: run_child("json", hash_seed=seed) for seed in SEEDS}
        assert len(set(outputs.values())) == 1, (
            "render_verdicts(json=True) produced different bytes under different "
            f"PYTHONHASHSEED values: { {s: len(o) for s, o in outputs.items()} }"
        )

    def test_table_bytes_are_identical_across_hash_seeds(self) -> None:
        outputs = {seed: run_child("table", hash_seed=seed) for seed in SEEDS}
        assert len(set(outputs.values())) == 1, (
            "render_verdicts(json=False) produced different bytes under different "
            f"PYTHONHASHSEED values: { {s: len(o) for s, o in outputs.items()} }"
        )

    def test_the_children_match_this_process_for_json(self) -> None:
        expected = render_child_direct("json")
        assert run_child("json", hash_seed="12345") == expected

    def test_the_children_match_this_process_for_the_table(self) -> None:
        expected = render_child_direct("table")
        assert run_child("table", hash_seed="12345") == expected

    def test_the_output_is_non_empty(self) -> None:
        assert len(run_child("json", hash_seed="1")) > 200
        assert len(run_child("table", hash_seed="1")) > 1000

    def test_the_trailing_newline_survives_the_pipe(self) -> None:
        assert run_child("json", hash_seed="1").endswith(b"}\n")
        assert run_child("table", hash_seed="1").endswith(b"\n")


class TestTheOutputDoesNotDependOnTheWorkingDirectory:
    """The honest form of "no cwd in the output": run children from different dirs."""

    def test_json_is_identical_from_repo_and_tmp(self, tmp_path: Path) -> None:
        from_repo = run_child("json", hash_seed="1", cwd=_REPO_ROOT)
        from_tmp = run_child("json", hash_seed="12345", cwd=tmp_path)
        assert from_repo == from_tmp

    def test_table_is_identical_from_repo_and_tmp(self, tmp_path: Path) -> None:
        from_repo = run_child("table", hash_seed="1", cwd=_REPO_ROOT)
        from_tmp = run_child("table", hash_seed="12345", cwd=tmp_path)
        assert from_repo == from_tmp

    def test_no_machine_specific_string_reaches_the_output(self, tmp_path: Path) -> None:
        ambient = {
            str(Path.cwd()),
            str(Path.cwd().resolve()),
            str(tmp_path),
            str(tmp_path.resolve()),
            str(Path.home()),
            str(_REPO_ROOT),
        }
        for value in ambient:
            assert value.encode("utf-8") not in run_child("table", hash_seed="1"), (
                f"{value!r} reached the table output"
            )
            assert value.encode("utf-8") not in run_child("json", hash_seed="1"), (
                f"{value!r} reached the json output"
            )