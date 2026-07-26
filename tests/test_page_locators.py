"""Tests for typed page locators: sheet index + printed folio capture."""
import json
from pathlib import Path

import pytest

from report import ConversionReport, write_report


def test_report_defaults_to_no_locator():
    r = ConversionReport(source="in.pdf", output="out.md", method="pymupdf")
    assert r.locator_type == "none"
    assert r.folio_pages == 0
    assert r.total_locator_pages == 0
    assert r.folio_coverage == 0.0
    assert r.folio_offset is None
    assert r.folio_offset_consistent is False


def test_report_locator_fields_round_trip(tmp_path):
    r = ConversionReport(
        source="in.pdf", output="out.md", method="pymupdf",
        locator_type="printed", folio_pages=20, total_locator_pages=319,
        folio_coverage=0.0627, folio_offset=-12, folio_offset_consistent=True,
    )
    p = tmp_path / "out.report.json"
    write_report(p, r)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["locator_type"] == "printed"
    assert data["folio_pages"] == 20
    assert data["folio_offset"] == -12
    assert data["folio_offset_consistent"] is True


def test_strip_running_headers_returns_three_tuples():
    import convert
    pages = [(i, f"Body text page {i}.\n{i + 10}") for i in range(1, 8)]
    result = convert._strip_running_headers(pages)
    assert all(len(t) == 3 for t in result)


def test_captures_bottom_standalone_folio():
    import convert
    # Sheet i carries printed folio i+10 as a standalone bottom line.
    pages = [(i, f"Body text for page {i}.\n{i + 10}") for i in range(1, 8)]
    result = convert._strip_running_headers(pages)
    folios = [folio for _, _, folio in result]
    assert folios == ["11", "12", "13", "14", "15", "16", "17"]
    # And the folio must be gone from the body.
    assert "11" not in result[0][1]


def test_captures_roman_folio():
    import convert
    romans = ["i", "ii", "iii", "iv", "v", "vi"]
    pages = [(i + 1, f"Front matter {i}.\n{r}") for i, r in enumerate(romans)]
    result = convert._strip_running_headers(pages)
    assert [f for _, _, f in result] == romans


def test_page_with_no_folio_yields_none():
    import convert
    pages = [(i, f"Body text page {i} with no page number.") for i in range(1, 8)]
    result = convert._strip_running_headers(pages)
    assert all(folio is None for _, _, folio in result)


def test_short_document_early_return_still_three_tuples():
    """The len < 5 early return must not leak 2-tuples to the caller."""
    import convert
    pages = [(1, "Only one page."), (2, "Second page.")]
    result = convert._strip_running_headers(pages)
    assert all(len(t) == 3 for t in result)
    assert all(folio is None for _, _, folio in result)


def test_pymupdf_emits_two_field_locator(tmp_path):
    import convert
    from tests import fixtures

    pdf = fixtures.build_foliated_pdf(tmp_path, pages=8, offset=-4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    # Sheet 5 carries printed folio 1.
    assert "<!-- Page sheet=5 folio=1 -->" in md
    assert "<!-- Page sheet=8 folio=4 -->" in md
    # Sheets 1-4 have no printed folio.
    assert "<!-- Page sheet=1 folio=none -->" in md
    # The old single-field format must be gone.
    assert "<!-- Page 5 -->" not in md


def test_pymupdf_reports_folio_coverage(tmp_path):
    import convert
    from tests import fixtures

    pdf = fixtures.build_foliated_pdf(tmp_path, pages=8, offset=-4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir)
    assert report.total_locator_pages == 8
    assert report.folio_pages == 4          # sheets 5,6,7,8
    assert report.folio_coverage == pytest.approx(0.5)
    assert report.locator_type == "printed"


def test_pymupdf_declares_sheet_only_when_no_folios(tmp_path):
    """An ebook-derived PDF has no printed folio; it must say so."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_text_pdf(tmp_path, pages=6, body="No folio here.")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pymupdf(pdf, out_dir)
    assert report.folio_pages == 0
    assert report.locator_type == "sheet-only"


def test_derive_offset_constant():
    import convert
    samples = {5: "1", 20: "16", 100: "96"}
    offset, consistent = convert._derive_folio_offset(samples)
    assert offset == -4
    assert consistent is True


def test_derive_offset_inconsistent_is_rejected():
    """A book that renumbers partway through must not be interpolated."""
    import convert
    samples = {5: "1", 20: "16", 100: "40"}
    offset, consistent = convert._derive_folio_offset(samples)
    assert consistent is False


def test_derive_offset_ignores_roman_folios():
    import convert
    samples = {2: "ii", 3: "iii", 10: "6", 20: "16", 30: "26"}
    offset, consistent = convert._derive_folio_offset(samples)
    assert offset == -4
    assert consistent is True


def test_derive_offset_needs_at_least_three_samples():
    import convert
    offset, consistent = convert._derive_folio_offset({5: "1", 20: "16"})
    assert consistent is False


def test_interpolates_folio_on_unnumbered_pages(tmp_path):
    """A page whose printed folio was lost to OCR still gets an address."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_foliated_pdf(tmp_path, pages=12, offset=-4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.folio_offset == -4
    assert report.folio_offset_consistent is True
    # Sheets 1-4 are genuinely before page 1 — they must stay `none`,
    # never a zero or negative folio.
    assert "<!-- Page sheet=1 folio=none -->" in md
    assert "folio=0" not in md
    assert "folio=-" not in md


def test_derive_offset_tolerates_non_ascii_digit_folio():
    """A superscript footnote marker must not crash the conversion.

    `"²".isdigit()` is True but `int("²")` raises ValueError. The arabic
    test is `.isascii() and .isdecimal()`, so the marker is simply ignored.
    """
    import convert
    samples = {5: "²", 10: "6", 20: "16", 30: "26"}
    offset, consistent = convert._derive_folio_offset(samples)
    assert offset == -4
    assert consistent is True


def test_derive_offset_ignores_arabic_indic_digits():
    import convert
    # U+0666 ARABIC-INDIC DIGIT SIX: isdigit() True, not ASCII decimal.
    samples = {5: "٦", 10: "6", 20: "16", 30: "26"}
    offset, consistent = convert._derive_folio_offset(samples)
    assert offset == -4
    assert consistent is True


def test_interpolates_missing_mid_body_folios(tmp_path):
    """Sheets whose printed folio was lost to extraction get filled in."""
    import convert
    from tests import fixtures

    # Sheets 5-12 print folios 1-8; sheets 7 and 9 lost their footer.
    pdf = fixtures.build_foliated_pdf(
        tmp_path, pages=12, offset=-4, skip_folios_on=(7, 9)
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.folio_offset == -4
    assert report.folio_offset_consistent is True
    # The two gaps are interpolated to their true printed numbers.
    assert "<!-- Page sheet=7 folio=3 -->" in md
    assert "<!-- Page sheet=9 folio=5 -->" in md
    # folio_pages counts CAPTURED folios only: sheets 5,6,8,10,11,12.
    assert report.folio_pages == 6
    # Front matter still refuses to invent a folio.
    assert "<!-- Page sheet=1 folio=none -->" in md
    assert "folio=0" not in md
    assert "folio=-" not in md


def test_no_extrapolation_past_the_last_captured_sample(tmp_path):
    """Beyond the captured span there is no evidence the offset holds.

    A real book's endnotes often restart at 1 and never survive extraction;
    they contribute no samples, so they cannot disagree. Extrapolating there
    would emit confident wrong numbers, so we clamp to [min, max] sample.
    """
    import convert
    from tests import fixtures

    # Sheets 5-12 print folios 1-8. Sheets 13-16 print nothing.
    pdf = fixtures.build_foliated_pdf(
        tmp_path, pages=16, offset=-4, skip_folios_on=(13, 14, 15, 16)
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.folio_offset == -4
    assert report.folio_offset_consistent is True
    for sheet in (13, 14, 15, 16):
        assert f"<!-- Page sheet={sheet} folio=none -->" in md
    # The would-be extrapolated numbers must appear nowhere.
    for bad in ("folio=9", "folio=10", "folio=11", "folio=12"):
        assert bad not in md


def test_renumbering_book_gets_no_interpolation_in_markdown(tmp_path):
    """The emission layer, not just the helper, must refuse an inconsistent book."""
    import convert
    from tests import fixtures

    pdf = fixtures.build_renumbering_pdf(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = convert.convert_with_pymupdf(pdf, out_dir)
    md = (out_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")

    assert report.folio_offset_consistent is False
    assert report.folio_offset is None
    # Sheets 12 and 14 lost their printed number. With two disagreeing
    # numbering runs we must emit `none`, never a guess.
    assert "<!-- Page sheet=12 folio=none -->" in md
    assert "<!-- Page sheet=14 folio=none -->" in md
    # Sheets 1-2 carry no printed number at all and stay `none`.
    assert "<!-- Page sheet=1 folio=none -->" in md
    assert "<!-- Page sheet=2 folio=none -->" in md
