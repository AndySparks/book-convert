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
