"""Tests for marker's page-locator capture.

marker is the only backend that works on a scanned book, so it is exactly
the backend a home-scanned print book depends on — and it was declaring
`page_numbering: "none"`, which would have routed every scan away from a
citable address permanently.

marker already reads the printed page number; it classifies the running head
as a PageHeader block and then discards it. `--paginate_output` recovers the
page boundary and `--keep_pageheader_in_output` /
`--keep_pagefooter_in_output` recover the furniture that carries the folio,
which we then strip back out.

Both bands matter. Ordinary pages carry a running head with the folio, but
chapter openers and full-page tables use a *drop folio* at the foot — which
is what a statistical appendix consists of. A head-only implementation read
0 folios across Boyatzis's entire appendix while appearing to work.

A rejected alternative — leaving marker's config alone and reading folios
from a blind crop of each page's margins — is documented in convert.py. It
made the body provably untouched but could not tell a page number from a
table cell, and produced samples too noisy to derive any offset at all.
"""
import convert
from report import ConversionReport


def marker_page(index, *lines):
    return f"{{{index}}}" + "-" * 48 + "\n\n" + "\n\n".join(lines) + "\n\n"


# A page must be longer than 2x the band depth or the leading and trailing
# bands overlap and a test cannot tell which one did the work.
FULL_PAGE_BODY = [f"Body line {n}." for n in range(1, 9)]


# --- _split_marker_pages ---------------------------------------------------


def test_split_marker_pages_returns_none_when_unpaginated():
    """No separators means marker ran without --paginate_output.

    This must be distinguishable from "page 0": a caller that treated it as
    a page index would emit confident wrong addresses for the whole book.
    """
    assert convert._split_marker_pages("Just some body text.\n") is None


def test_split_marker_pages_keeps_markers_page_indices():
    text = marker_page(58, "Body one.") + marker_page(59, "Body two.")
    assert [i for i, _ in convert._split_marker_pages(text)] == [58, 59]


def test_split_marker_pages_preserves_gaps_in_index():
    """marker numbers by sheet, so a blank page still advances the count."""
    text = marker_page(10, "A.") + marker_page(12, "B.")
    assert [i for i, _ in convert._split_marker_pages(text)] == [10, 12]


# --- furniture stripping ---------------------------------------------------


def test_running_head_and_folio_are_captured_and_removed():
    pages = convert._split_marker_pages(
        marker_page(58, "Job Performance as a Criterion Measure", "43", "Body text here.")
        + marker_page(60, "Job Performance as a Criterion Measure", "45", "More body.")
        + marker_page(62, "Job Performance as a Criterion Measure", "47", "Yet more."))
    headers = convert._marker_recurring_lines(pages)
    folio, body = convert._strip_marker_page_furniture(pages[0][1], headers, set())
    assert folio == "43"
    assert body.strip() == "Body text here."


def test_running_head_needs_repetition_so_body_prose_survives():
    """Frequency is the whole safety argument for stripping: a running head
    appears on many pages, an opening sentence appears once."""
    pages = convert._split_marker_pages(
        marker_page(5, "A singular opening sentence.", "Rest of the page.")
        + marker_page(6, "A different opening.", "Rest again."))
    headers = convert._marker_recurring_lines(pages)
    assert headers == set()
    _folio, body = convert._strip_marker_page_furniture(pages[0][1], headers, set())
    assert body.startswith("A singular opening sentence.")


def test_stripping_stops_at_first_body_line():
    pages = convert._split_marker_pages(
        marker_page(1, "Running Head", "Body.", "Running Head")
        + marker_page(2, "Running Head", "Other.")
        + marker_page(3, "Running Head", "Third."))
    headers = convert._marker_recurring_lines(pages)
    _folio, body = convert._strip_marker_page_furniture(pages[0][1], headers, set())
    assert "Body." in body
    assert body.count("Running Head") == 1


def test_a_recurring_markdown_heading_is_never_stripped():
    """Content, not furniture. Boyatzis repeats '## THE COMPETENT MANAGER' on
    three half-titles; frequency alone would delete it, and marker's own
    default output keeps it. This was a real 3-line data loss."""
    text = "".join(marker_page(i, "## THE COMPETENT MANAGER", "Body.") for i in (1, 2, 3, 4))
    pages = convert._split_marker_pages(text)
    headers = convert._marker_recurring_lines(pages)
    assert "## THE COMPETENT MANAGER" in headers          # it does recur...
    _folio, body = convert._strip_marker_page_furniture(pages[0][1], headers, set())
    assert "## THE COMPETENT MANAGER" in body             # ...but survives


def test_drop_folio_at_the_foot_of_the_page_is_captured():
    """An appendix table page has no running head: the caption is the first
    block and the folio sits alone at the bottom. The body is long enough
    that the folio is outside the leading band, so this fails if the trailing
    band is not read."""
    pages = convert._split_marker_pages(
        marker_page(300, "TABLE A-16 Mean Motive and Trait Levels", *FULL_PAGE_BODY, "285"))
    folio, body = convert._strip_marker_page_furniture(pages[0][1], set(), set())
    assert folio == "285"
    assert "285" not in body
    assert body.strip().startswith("TABLE A-16")


def test_running_head_folio_is_captured_from_the_leading_band():
    """Mirror of the drop-folio case, so neither band can be dropped."""
    pages = convert._split_marker_pages(
        marker_page(58, "Job Performance as a Criterion Measure", "43", *FULL_PAGE_BODY))
    folio, body = convert._strip_marker_page_furniture(pages[0][1], set(), set())
    assert folio == "43"
    assert body.strip().endswith("Body line 8.")


def test_footer_folio_does_not_eat_a_trailing_table_row():
    pages = convert._split_marker_pages(
        marker_page(300, "| Stage IV | 1.525 | 1.612 |", "285"))
    _folio, body = convert._strip_marker_page_furniture(pages[0][1], set(), set())
    assert "| Stage IV | 1.525 | 1.612 |" in body


def test_trailing_number_run_is_not_consumed_wholesale():
    """A page can legitimately end in a run of bare numbers — an index
    column, or a table whose final rows are unlabelled. Without a bound,
    stripping would walk up the run and delete real content invisibly."""
    pages = convert._split_marker_pages(
        marker_page(300, "Index", *FULL_PAGE_BODY, "101", "102", "103", "104", "105"))
    _folio, body = convert._strip_marker_page_furniture(pages[0][1], set(), set())
    remaining = [l for l in body.split("\n") if l.strip()]
    assert "101" in remaining, "stripping walked past its bound into page content"


def test_folio_zero_is_rejected_outright():
    """No book prints page 0, so a captured '0' is always a misread. This
    needs no evidence from the rest of the book."""
    assert convert._is_marker_folio("0") is False
    assert convert._is_marker_folio("1") is True
    pages = convert._split_marker_pages(
        marker_page(24, "0", "The Purpose of this Study", *FULL_PAGE_BODY))
    folio, _body = convert._strip_marker_page_furniture(pages[0][1], set(), set())
    assert folio != "0"


def test_roman_front_matter_folio_is_captured():
    pages = convert._split_marker_pages(marker_page(8, "xiv", "Preface text."))
    folio, body = convert._strip_marker_page_furniture(pages[0][1], set(), set())
    assert folio == "xiv"
    assert body.strip() == "Preface text."


# --- _rewrite_marker_page_locators ----------------------------------------


def _rewrite(tmp_path, text):
    target = tmp_path / "book.md"
    target.write_text(text, encoding="utf-8")
    report = ConversionReport(source="b.pdf", output=str(target), method="marker")
    convert._rewrite_marker_page_locators(target, report)
    return target.read_text(encoding="utf-8"), report


def test_rewrite_emits_typed_locators(tmp_path):
    text = (marker_page(58, "Running Head", "43", "First.")
            + marker_page(59, "Running Head", "44", "Second.")
            + marker_page(60, "Running Head", "45", "Third."))
    out, report = _rewrite(tmp_path, text)
    assert "<!-- page_pdf=58 page_printed=43 -->" in out
    assert "<!-- page_pdf=60 page_printed=45 -->" in out
    assert report.page_numbering == "printed"
    assert report.page_printed_offset == -15
    assert report.page_printed_offset_consistent is True


def test_rewrite_interpolates_between_samples(tmp_path):
    text = (marker_page(58, "Running Head", "43", "First.")
            + marker_page(59, "Running Head", "Chapter opener with no folio.")
            + marker_page(60, "Running Head", "45", "Third.")
            + marker_page(61, "Running Head", "46", "Fourth."))
    out, report = _rewrite(tmp_path, text)
    assert "<!-- page_pdf=59 page_printed=44 -->" in out
    assert report.page_printed_count == 3          # interpolated pages are not captured
    assert report.page_locator_count == 4


def test_rewrite_refuses_to_extrapolate_past_the_last_sample(tmp_path):
    """Endnotes often restart numbering. Outside the sampled span there is no
    evidence the offset still holds, so emit none rather than a guess."""
    text = (marker_page(10, "Running Head", "5", "A.")
            + marker_page(11, "Running Head", "6", "B.")
            + marker_page(12, "Running Head", "7", "C.")
            + marker_page(40, "Running Head", "Endnotes with no folio."))
    out, _report = _rewrite(tmp_path, text)
    assert "<!-- page_pdf=40 page_printed=none -->" in out


def test_front_matter_before_the_first_sample_gets_no_page_number(tmp_path):
    """The span clamp is what prevents interpolating backwards into roman
    front matter. (`candidate >= 1` in the rewrite is belt-and-braces from
    the pymupdf path; with a consistent offset and a span clamped to real
    printed numbers it is unreachable, so no test claims to exercise it.)"""
    text = (marker_page(20, "Running Head", "1", "Chapter one.")
            + marker_page(21, "Running Head", "2", "More.")
            + marker_page(22, "Running Head", "3", "More still.")
            + marker_page(2, "Running Head", "Front matter."))
    out, _report = _rewrite(tmp_path, text)
    assert "<!-- page_pdf=2 page_printed=none -->" in out
    assert "page_printed=0" not in out


def test_misread_folio_is_replaced_by_the_interpolated_value(tmp_path):
    """End to end: a captured number contradicting the book's offset must not
    reach the output, and the reader must be told it was overridden."""
    text = "".join(
        marker_page(s, "Running Head", "30" if s == 54 else str(s - 15), f"Body {s}.")
        for s in range(20, 60))
    out, report = _rewrite(tmp_path, text)
    assert "<!-- page_pdf=54 page_printed=39 -->" in out
    assert "<!-- page_pdf=54 page_printed=30 -->" not in out
    assert any("misread" in w and "page_pdf=54" in w for w in report.warnings)
    assert report.page_printed_count == 39


def test_rewrite_marks_unpaginated_output_as_uncitable(tmp_path):
    """A caller can override the locator flags via --marker-args. That must
    degrade to an explicit 'none' plus a warning, not a crash."""
    out, report = _rewrite(tmp_path, "Body text with no separators.\n")
    assert out == "Body text with no separators.\n"
    assert report.page_numbering == "none"
    assert any("not paginated" in w for w in report.warnings)


def test_rewrite_reports_pdf_only_when_no_folio_is_readable(tmp_path):
    """Deep Work has no printed numbers anywhere. The sheet index is still a
    real address, so it is pdf_only, not none."""
    text = marker_page(1, "Body one.") + marker_page(2, "Body two.")
    out, report = _rewrite(tmp_path, text)
    assert report.page_numbering == "pdf_only"
    assert "<!-- page_pdf=1 page_printed=none -->" in out


def test_locator_args_request_both_bands():
    """Regression guard: dropping the footer flag silently halves capture on
    any book with drop folios."""
    assert "--paginate_output" in convert.MARKER_LOCATOR_ARGS
    assert "--keep_pageheader_in_output" in convert.MARKER_LOCATOR_ARGS
    assert "--keep_pagefooter_in_output" in convert.MARKER_LOCATOR_ARGS


def test_marker_is_no_longer_hardcoded_as_uncitable():
    """Regression guard for the bug this file exists to fix."""
    assert "marker" not in convert.BACKEND_PAGE_NUMBERING
    report = ConversionReport(source="b.pdf", output="o.md", method="marker",
                              page_numbering="printed")
    convert._apply_backend_page_numbering(report)
    assert report.page_numbering == "printed"


# --- consensus outlier rejection -------------------------------------------
#
# Strict unanimity protected interpolated numbers but left CAPTURED ones
# unguarded, so a single misread digit both blocked interpolation for the
# rest of the book and was published verbatim as a page number. Boyatzis
# printed 9 and 39 on two pages that OCR read as "0" and "30".
#
# Rejecting an outlier is only safe when the consensus is overwhelming and
# the dissent is scattered: a book that genuinely renumbers produces a
# CONTIGUOUS RUN at the new offset, never isolated singletons.


def samples(offset, sheets, overrides=None):
    """Captured-folio dict with a constant offset, plus explicit overrides."""
    out = {s: str(s + offset) for s in sheets}
    out.update({k: str(v) for k, v in (overrides or {}).items()})
    return out


def test_isolated_outlier_is_rejected_when_consensus_is_overwhelming():
    s = samples(-15, range(20, 60), {54: 30})   # 54 should print 39
    offset, consistent = convert._derive_page_offset(s)
    assert (offset, consistent) == (-15, True)
    assert convert._page_offset_outliers(s, offset) == {54}


def test_contiguous_dissent_is_a_renumbering_and_still_refuses():
    """The guard that keeps this from flattening a real second sequence.

    Enough samples to clear the agreement threshold, so this proves the RUN
    rule rather than the threshold.
    """
    s = samples(-15, range(20, 70))
    for sheet in range(60, 70):            # endnotes restarting at 1
        s[sheet] = str(sheet - 59)
    assert convert._derive_page_offset(s) == (None, False)


def test_two_adjacent_dissenters_are_enough_to_refuse():
    """Adjacency is the signal, not volume — a restart begins somewhere."""
    s = samples(-15, range(20, 60), {54: 30, 55: 31})
    assert convert._derive_page_offset(s) == (None, False)


def test_weak_agreement_refuses():
    """Dissenters spaced far enough apart to clear the run guard, so this
    isolates the agreement threshold rather than passing on adjacency.

    Widespread disagreement means the offset model itself is wrong for this
    book — not that a few digits were misread.
    """
    s = samples(-15, range(20, 60))
    dissenters = list(range(20, 60, 6))    # 7 of 40, none adjacent
    for sheet in dissenters:
        s[sheet] = str(sheet - 15 + 3)
    assert max(b - a for a, b in zip(dissenters, dissenters[1:])) > 2
    assert convert._derive_page_offset(s) == (None, False)


def test_small_non_unanimous_sample_sets_cannot_reach_consensus():
    """Below 20 samples any dissent drops agreement under the threshold, so
    the original strict rule still governs small books. Documented as a
    property rather than a separate guard, because a minimum-samples check
    would be unreachable."""
    for n in (5, 10, 19):
        s = samples(-15, range(20, 20 + n), {21: 999})
        assert convert._derive_page_offset(s) == (None, False), n


def test_unanimous_samples_are_unaffected():
    s = samples(-15, range(20, 60))
    assert convert._derive_page_offset(s) == (-15, True)
    assert convert._page_offset_outliers(s, -15) == set()


def test_outliers_are_empty_when_no_offset_was_derived():
    s = samples(-15, range(20, 60), {54: 30, 55: 31})
    assert convert._page_offset_outliers(s, None) == set()


# --- flag plumbing ---------------------------------------------------------


def _fake_marker(seen, body):
    """Stand in for marker_single: record the command, write a paginated file."""
    from pathlib import Path

    class FakeProc:
        def __init__(self, cmd, **_kw):
            seen["cmd"] = cmd
            out = Path(cmd[cmd.index("--output_dir") + 1]) / "book"
            out.mkdir(parents=True, exist_ok=True)
            (out / "book.md").write_text(body, encoding="utf-8")
            self.stdout = iter(())

        def wait(self):
            return 0

    return FakeProc


def test_locator_flags_actually_reach_marker(tmp_path, monkeypatch):
    """The constant being correct does not prove it is passed. Without the
    flags marker emits no separators, and every scanned book silently loses
    its page addresses again — the exact regression this work undoes.
    """
    seen = {}
    body = (marker_page(10, "Running Head", "1", "Body one.")
            + marker_page(11, "Running Head", "2", "Body two.")
            + marker_page(12, "Running Head", "3", "Body three."))
    monkeypatch.setattr(convert.subprocess, "Popen", _fake_marker(seen, body))
    monkeypatch.setattr(convert, "apply_table_signals", lambda *a, **k: None)
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()                      # convert_book normally creates this

    report = convert.convert_with_marker(pdf, out_dir)

    for flag in convert.MARKER_LOCATOR_ARGS:
        assert flag in seen["cmd"], f"{flag} never reached marker_single"
    assert report.page_numbering == "printed"


def test_user_marker_args_are_appended_not_substituted(tmp_path, monkeypatch):
    """`--marker-args` must not displace the locator flags: table quality and
    page addressing are independent concerns."""
    seen = {}
    body = (marker_page(10, "Running Head", "1", "Body one.")
            + marker_page(11, "Running Head", "2", "Body two.")
            + marker_page(12, "Running Head", "3", "Body three."))
    monkeypatch.setattr(convert.subprocess, "Popen", _fake_marker(seen, body))
    monkeypatch.setattr(convert, "apply_table_signals", lambda *a, **k: None)
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    convert.convert_with_marker(pdf, out_dir, marker_args=["--use_llm"])

    assert "--use_llm" in seen["cmd"]
    for flag in convert.MARKER_LOCATOR_ARGS:
        assert flag in seen["cmd"]
