"""The PDF-to-Markdown converter, specified by failing tests (aspect `pdf-input/frontend`).

Phase P1 (RED) pinned the contract for `src/plumb/pdf/` before the package existed;
phase P2 (GREEN) extends it with the fallback path, the table shape, and the drop
accounting. The four things pinned here are the four the `seam` aspect will build on:

- **Fixture conversion** (a): `pdf_to_markdown(pdf_bytes)` on the real Cureus PDF
  returns Markdown-equivalent text carrying ATX `## ` headings — the abstract heading
  among them — plus an H1 title line and GFM pipe-table lines. The glued-label quirk
  (`AbstractThis review...` in the JATS-derived Markdown) must never survive the
  conversion, and the output must round-trip through `extract_claims` without error.
- **Determinism in-process** (b): identical bytes produce an identical string.
- **Value line-join** (c): a numeric token split across a line break (`0.0` + newline
  + `3`) joins back into `0.03`; an unbroken value is unchanged; a break between two
  distinct values is never joined into one invented number.
- **No network, structurally** (d): the module source is scanned — AST for imports
  and name references, text for the tokens themselves — and no network-capable name
  appears. The guard is self-tested against synthetic offenders, because a guard
  that cannot fire is a guard that proves nothing.

The cross-process byte-identity bar (acceptance criterion 2 of the PRD) is pinned in
phase P3; the full-suite no-network blocker (`tests/conftest.py`) already covers every
test here.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest

from plumb.extract.pipeline import extract_claims
from plumb.pdf import PdfInputError, pdf_to_markdown, pdf_to_markdown_with_stats
from plumb.pdf.convert import (
    _join_wrapped_values,
    _label_heading,
    _shape_heading,
    _split_glued_label,
)

_FIXTURE = Path("fixtures/papers/PMC13134363.pdf")
_PDF_PACKAGE = Path(__file__).parents[2] / "src" / "plumb" / "pdf"
_SRC = Path(__file__).parents[2] / "src"
_THIS_DIR = Path(__file__).parent


class TestFixtureConversion:
    """The real Cureus PDF becomes Markdown-equivalent text with the C1 section hints."""

    def test_the_converted_text_contains_an_abstract_heading(self) -> None:
        markdown = pdf_to_markdown(_FIXTURE.read_bytes())
        headings = [line for line in markdown.splitlines() if line.startswith("## ")]
        assert headings, "no ATX level-2 headings in the converted text"
        assert any("abstract" in heading.lower() for heading in headings), (
            "the abstract section heading did not survive conversion"
        )

    def test_the_converted_text_contains_a_title_heading(self) -> None:
        # The `# Title` H1 must survive so H1-level context is not flattened away
        # (aspect spec: "The `# Title` H1 ... emit a title line").
        markdown = pdf_to_markdown(_FIXTURE.read_bytes())
        assert any(line.startswith("# ") for line in markdown.splitlines()), (
            "no H1 title line in the converted text"
        )

    def test_no_glued_section_label_survives(self) -> None:
        # The JATS-to-Markdown fixture glues the label to the prose
        # ("AbstractThis review..."); the converter must normalize that gluing,
        # never emit it.
        markdown = pdf_to_markdown(_FIXTURE.read_bytes())
        assert "AbstractThis" not in markdown

    def test_the_converted_text_contains_gfm_pipe_table_lines(self) -> None:
        markdown = pdf_to_markdown(_FIXTURE.read_bytes())
        assert any(line.startswith("|") for line in markdown.splitlines()), (
            "no GFM pipe-table lines in the converted text"
        )

    def test_the_converted_text_round_trips_through_the_c1_seam(self) -> None:
        # The seam (`extract_claims(raw: str)`) must accept the converted text and
        # run to completion; claim-by-claim equality vs the Markdown path is the
        # `seam` aspect's bar, not asserted here.
        markdown = pdf_to_markdown(_FIXTURE.read_bytes())
        claims, rejections = extract_claims(markdown)
        assert isinstance(claims, tuple)
        assert isinstance(rejections, tuple)


class TestInProcessDeterminism:
    def test_identical_bytes_give_identical_text(self) -> None:
        payload = _FIXTURE.read_bytes()
        assert pdf_to_markdown(payload) == pdf_to_markdown(payload)


class TestValueLineJoin:
    """The `_join_wrapped_values` seam: values split across a line break re-join.

    `normalize_text` does not collapse whitespace (location.py), so a PDF line break
    inside a value would change its claim id vs the Markdown path; the converter
    must undo the break inside numeric tokens — and only inside numeric tokens.
    """

    def test_a_value_split_across_a_line_break_is_joined(self) -> None:
        assert _join_wrapped_values("0.0\n3") == "0.03"

    def test_an_unbroken_value_is_unchanged(self) -> None:
        assert _join_wrapped_values("0.03") == "0.03"

    def test_a_non_numeric_line_break_becomes_a_space(self) -> None:
        # A legitimate break between words is kept as a break; the rule is
        # numeric-token-scoped, never word-inventing.
        assert _join_wrapped_values("nineteen\nstudies") == "nineteen studies"

    def test_two_distinct_values_are_never_joined_into_one(self) -> None:
        # The negative control for "never invent": two values stacked in one cell
        # must not fuse into a single invented number.
        assert _join_wrapped_values("835,784\n1,705") == "835,784 1,705"


class TestGluedLabelSplit:
    """The `_split_glued_label` seam behind the glued-label normalization."""

    def test_a_known_label_glued_to_prose_splits_off(self) -> None:
        assert _split_glued_label("AbstractThis review aimed") == "Abstract"

    def test_a_clean_label_line_is_not_split(self) -> None:
        assert _split_glued_label("Abstract") is None

    def test_prose_that_merely_contains_a_label_word_is_untouched(self) -> None:
        assert _split_glued_label("This review aimed") is None

    def test_a_word_that_only_starts_with_a_label_is_untouched(self) -> None:
        # "Abstractly" begins with the label but continues the word; splitting it
        # would invent a heading where the author wrote prose.
        assert _split_glued_label("Abstractly, prevalence") is None


class TestCorruptInput:
    def test_garbage_bytes_raise_pdf_input_error(self) -> None:
        # A harness-side failure is a named exception with a named cause; the
        # converter never guesses (plan: "Unreadable/corrupt PDF bytes -> raise a
        # named exception (`PdfInputError`) with the cause").
        with pytest.raises(PdfInputError):
            pdf_to_markdown(b"this is not a pdf")


class TestBodySizeAbstractRescue:
    """An abstract heading set at body size must still survive (MDPI/Sensors/Springer).

    Those journals render "Abstract" in the body font on the title's page, where a
    real font signal exists — so the size rule cannot promote it and the broad
    shape rules would over-promote the sidebar. The exact-label rescue is the
    middle path, and it is pinned on the real fixtures.
    """

    @pytest.mark.parametrize(
        "pmcid",
        ("PMC13298092", "PMC13332965", "PMC13363872"),
    )
    def test_the_abstract_heading_is_recovered(self, pmcid: str) -> None:
        markdown = pdf_to_markdown(
            Path(f"fixtures/papers/{pmcid}.pdf").read_bytes()
        )
        headings = [line for line in markdown.splitlines() if line.startswith("## ")]
        assert any("abstract" in heading.lower() for heading in headings), (
            f"{pmcid}: no abstract heading in the converted text"
        )

    def test_only_an_exact_section_label_is_rescued(self) -> None:
        assert _label_heading("Abstract") == "## "
        assert _label_heading("References") == "## "
        assert _label_heading("Setting") is None
        assert _label_heading("Corresponding author: John K. Muthuka") is None


class TestShapeFallbackHeading:
    """The named fallback for PDFs without font-size signals (plan: line-shape rules).

    Fires only when no run is clearly larger than the page body; the fixtures carry
    font signals, so these rules are pinned by unit test rather than by fixture.
    """

    def test_a_title_case_short_line_is_a_heading(self) -> None:
        assert _shape_heading("Materials and methods") == "## "

    def test_a_single_word_section_label_is_a_heading(self) -> None:
        assert _shape_heading("References") == "## "

    def test_a_sidebar_info_line_is_not_a_heading(self) -> None:
        assert _shape_heading("Review began 03/15/2026") is None

    def test_a_page_number_line_is_not_a_heading(self) -> None:
        assert _shape_heading("5 of 21") is None

    def test_a_sentence_is_not_a_heading(self) -> None:
        assert _shape_heading("This review aimed to estimate the global prevalence.") is None

    def test_a_long_line_is_not_a_heading(self) -> None:
        assert (
            _shape_heading(
                "The Quick Brown Fox Jumps Over The Lazy Dog And Keeps Running On "
                "And On And On Across The Field"
            )
            is None
        )


class TestTableEmission:
    """The fixture's tables must come out as well-formed GFM pipe tables."""

    def test_each_pipe_table_is_well_formed(self) -> None:
        markdown = pdf_to_markdown(_FIXTURE.read_bytes())
        blocks: list[list[str]] = []
        current: list[str] = []
        for line in markdown.splitlines():
            if line.startswith("|"):
                current.append(line)
            elif current:
                blocks.append(current)
                current = []
        if current:
            blocks.append(current)
        assert blocks, "no GFM pipe rows in the converted text"
        for block in blocks:
            assert any(set(line) <= set("| -:") for line in block), (
                "a pipe block has no GFM delimiter row (a table needs a header, "
                "a delimiter, and rows)"
            )
            counts = {line.count("|") for line in block}
            assert len(counts) == 1, (
                f"pipe rows disagree on cell count inside one table: {counts}"
            )

    def test_a_table_value_survives_inside_a_cell(self) -> None:
        markdown = pdf_to_markdown(_FIXTURE.read_bytes())
        cells = [line for line in markdown.splitlines() if line.startswith("|")]
        assert any("0.20" in line for line in cells), (
            "a known table value did not survive cell reconstruction"
        )


class TestConversionStats:
    """The drop accounting the seam tests report (spec: never a silent pass)."""

    def test_stats_are_reported_for_the_fixture(self) -> None:
        _markdown, stats = pdf_to_markdown_with_stats(_FIXTURE.read_bytes())
        assert stats.pages == 21
        assert stats.headings_emitted >= 8, (
            "fewer `## ` headings than the Markdown fixture carries"
        )

    def test_unmappable_table_segments_are_counted_not_hidden(self) -> None:
        # The `[10]`-style citations inside table cells map to no column and must
        # be dropped *and counted* — the fixture exercises the drop path.
        _markdown, stats = pdf_to_markdown_with_stats(_FIXTURE.read_bytes())
        assert stats.dropped_table_segments > 0


# --------------------------------------------------------------------------------
# Cross-process byte identity (acceptance criterion 2 of the PRD)
# --------------------------------------------------------------------------------
#
# In-process determinism cannot see hash-order dependence: inside one interpreter,
# dict and set iteration order are stable, so a test that calls the converter twice
# passes while the contract is broken. The load-bearing bar is the same PDF bytes
# converted in *fresh interpreters* under different `PYTHONHASHSEED` values, written
# raw to stdout and compared as bytes — the `test_determinism.py` pattern applied to
# this package. `subprocess` is deliberately outside `conftest.py`'s network
# blocker; nothing here reaches outward.

SEEDS = ("0", "1", "12345", "random")
FIXED_SEEDS = ("0", "1", "12345")


def child_render(payload: str, pdf_path: str) -> None:
    """Entry point for the spawned interpreter: raw bytes to stdout, nothing else.

    `probe` is the control payload: it reports what this interpreter's `hash()`
    does, the one thing that *must* differ between children under different seeds
    — without it, a cross-seed byte-identity pass could mean the seed never
    reached the child.
    """
    if payload == "probe":
        seen = tuple(hash(word) for word in ("plumb", "AUC", "0.87", "µg/mL"))
        sys.stdout.buffer.write(repr(seen).encode("utf-8"))
        return
    from plumb.pdf import pdf_to_markdown

    markdown = pdf_to_markdown(Path(pdf_path).read_bytes())
    sys.stdout.buffer.write(markdown.encode("utf-8"))
    sys.stdout.buffer.flush()


_CHILD_PROGRAM = """\
import sys

# argv[1] is tests/pdf: the child imports the same module that will compare its
# output, so the two cannot drift apart.
sys.path.insert(0, sys.argv[1])

from test_convert import child_render

child_render(sys.argv[2], sys.argv[3])
"""


def run_child(payload: str, *, hash_seed: str) -> bytes:
    """Run one fresh interpreter under `hash_seed` and return its stdout bytes."""
    env = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        "PYTHONPATH": str(_SRC),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHILD_PROGRAM,
            str(_THIS_DIR),
            payload,
            str(_FIXTURE.resolve()),
        ],
        env=env,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, (
        f"child failed (payload={payload!r}, seed={hash_seed!r}):\n"
        f"{result.stderr.decode('utf-8', 'replace')}"
    )
    assert isinstance(result.stdout, bytes)
    return result.stdout


class TestCrossProcessByteIdentity:
    """The same PDF bytes, in fresh interpreters, produce the same bytes."""

    def test_the_hash_seed_really_varies_in_the_child(self) -> None:
        probes = {seed: run_child("probe", hash_seed=seed) for seed in FIXED_SEEDS}
        assert len(set(probes.values())) == len(FIXED_SEEDS), (
            "the children agree about hash() under different PYTHONHASHSEED values, "
            "so the seed is not reaching them and the byte-identity tests below "
            f"prove nothing: {probes}"
        )

    def test_the_bytes_are_identical_across_hash_seeds(self) -> None:
        outputs = {seed: run_child("render", hash_seed=seed) for seed in SEEDS}
        distinct = set(outputs.values())
        assert len(distinct) == 1, (
            "pdf_to_markdown produced different bytes under different "
            f"PYTHONHASHSEED values: { {s: len(o) for s, o in outputs.items()} }"
        )

    def test_the_child_bytes_match_this_process(self) -> None:
        expected = pdf_to_markdown(_FIXTURE.read_bytes()).encode("utf-8")
        assert run_child("render", hash_seed="12345") == expected

    def test_the_output_is_non_empty_and_carries_the_document(self) -> None:
        # Vacuity control: two empty documents are also byte-identical.
        out = run_child("render", hash_seed="1")
        assert len(out) > 10_000
        assert b"## Abstract" in out
        assert out.endswith(b"\n")

    def test_the_output_is_bytes_not_text(self) -> None:
        out = run_child("render", hash_seed="1")
        assert isinstance(out, bytes)
        # Decodable, but the comparison above is made on the bytes.
        assert "©" in out.decode("utf-8")
#
# `src/plumb/extract/` has its own AST allowlist (`test_determinism.py:1048-1062`),
# and this package is deliberately outside that scan. So it carries its own guard:
# no module under `src/plumb/pdf/` may import, reference, or even mention a
# network-capable name. The check is structural where it can be (AST import roots
# and name references) and textual where the task names exact tokens — and both
# halves are self-tested, because a guard that cannot fire proves nothing.

_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"socket", "urllib", "http", "requests", "subprocess"}
)

_FORBIDDEN_NAMES = frozenset(
    {"socket", "urllib", "http", "requests", "subprocess", "environ", "getenv"}
)

#: Exact substrings that may not appear in the source text at all. `os.environ` is
#: written out (not `environ`) because the substring `environ` lives inside the word
#: "environment", and a guard that fires on prose gets disabled.
_FORBIDDEN_TOKENS = ("socket", "urllib", "http", "requests", "subprocess", "os.environ")


# --------------------------------------------------------------------------------
# The source-level no-network guard, applied to src/plumb/pdf/
# --------------------------------------------------------------------------------
#
# `src/plumb/extract/` has its own AST allowlist (`test_determinism.py:1048-1062`),
# and this package is deliberately outside that scan. So it carries its own guard:
# no module under `src/plumb/pdf/` may import, reference, or even mention a
# network-capable name. The check is structural where it can be (AST import roots
# and name references) and textual where the task names exact tokens — and both
# halves are self-tested, because a guard that cannot fire proves nothing.

def pdf_sources() -> dict[str, str]:
    """Every module of the package, by file name, read as text."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_PDF_PACKAGE.rglob("*.py"))
    }


def imported_roots(tree: ast.Module) -> set[str]:
    """The top-level package of every import, from import nodes only."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def referenced_names(tree: ast.Module) -> set[str]:
    """Every name read and every attribute touched, called or not."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


class TestNoNetworkInThePdfPackage:
    """The module and the pinned dependency must never touch a socket or a hostname."""

    def test_the_scan_actually_covers_the_package(self) -> None:
        # Vacuity control: a guard that scans nothing passes forever.
        names = set(pdf_sources())
        assert {"__init__.py", "convert.py"} <= names

    def test_no_module_imports_a_network_capable_package(self) -> None:
        offenders = {
            name: sorted(imported_roots(ast.parse(source)) & _FORBIDDEN_IMPORT_ROOTS)
            for name, source in pdf_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}

    def test_no_module_references_a_network_or_environment_name(self) -> None:
        # Referenced, not merely called: `os.environ` is a read, not a call, and a
        # Call-node walk would miss it.
        offenders = {
            name: sorted(referenced_names(ast.parse(source)) & _FORBIDDEN_NAMES)
            for name, source in pdf_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}

    def test_no_network_capable_token_appears_in_the_source_text(self) -> None:
        offenders = {
            name: [token for token in _FORBIDDEN_TOKENS if token in source]
            for name, source in pdf_sources().items()
        }
        assert not {k: v for k, v in offenders.items() if v}

    # -- the guard fires, and stays silent on clean code -------------------------

    def test_the_import_guard_fires_on_a_module_that_imports_socket(self) -> None:
        tree = ast.parse("import socket\n")
        assert imported_roots(tree) & _FORBIDDEN_IMPORT_ROOTS == {"socket"}

    def test_the_reference_guard_fires_on_os_dot_environ(self) -> None:
        tree = ast.parse("import os\nx = os.environ\n")
        assert referenced_names(tree) & _FORBIDDEN_NAMES == {"environ"}

    def test_the_token_guard_fires_on_source_that_mentions_urllib(self) -> None:
        assert [t for t in _FORBIDDEN_TOKENS if t in "import urllib.request"] == [
            "urllib"
        ]