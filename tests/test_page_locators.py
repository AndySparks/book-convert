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
