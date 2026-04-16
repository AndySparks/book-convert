"""Tests for the ConversionReport dataclass and JSON sidecar writer."""
import json
from pathlib import Path

import pytest

from report import ConversionReport, write_report


def test_conversion_report_defaults():
    r = ConversionReport(
        source="input/book.pdf",
        output="output/book.md",
        method="pymupdf",
    )
    assert r.total_pages == 0
    assert r.pages_with_text == 0
    assert r.ocr_pages == 0
    assert r.two_column_pages == 0
    assert r.extracted_assets == 0
    assert r.quality_score == 1.0
    assert r.skipped_toc_pages == 0
    assert r.warnings == []


def test_conversion_report_to_dict_round_trips():
    r = ConversionReport(
        source="input/book.pdf",
        output="output/book.md",
        method="pymupdf",
        total_pages=214,
        pages_with_text=210,
        two_column_pages=0,
        extracted_assets=12,
        quality_score=0.95,
        skipped_toc_pages=2,
        warnings=["example warning"],
    )
    d = r.to_dict()
    assert d["source"] == "input/book.pdf"
    assert d["method"] == "pymupdf"
    assert d["extracted_assets"] == 12
    assert d["warnings"] == ["example warning"]


def test_write_report_produces_parseable_json(tmp_path):
    r = ConversionReport(
        source="input/book.pdf",
        output="output/book.md",
        method="pymupdf",
        total_pages=10,
        quality_score=0.88,
    )
    report_path = tmp_path / "book.report.json"
    write_report(report_path, r)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["method"] == "pymupdf"
    assert data["quality_score"] == 0.88


def test_write_report_pretty_prints(tmp_path):
    """Sidecar should be indented for human inspection, not minified."""
    r = ConversionReport(
        source="in.pdf", output="out.md", method="pymupdf",
    )
    p = tmp_path / "out.report.json"
    write_report(p, r)
    text = p.read_text(encoding="utf-8")
    assert "\n" in text
    assert text.startswith("{")


def test_convert_with_pymupdf_writes_sidecar(tmp_path):
    """convert_with_pymupdf should write a .report.json next to the .md output."""
    from tests import fixtures
    import convert

    pdf = fixtures.build_text_pdf(tmp_path, pages=3)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = convert.convert_with_pymupdf(pdf, out_dir)

    # New return type: ConversionReport, not bool
    assert isinstance(result, ConversionReport)
    assert result.method == "pymupdf"
    assert result.total_pages == 3
    assert result.pages_with_text == 3

    sidecar = out_dir / f"{pdf.stem}.report.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["method"] == "pymupdf"
    assert data["total_pages"] == 3
