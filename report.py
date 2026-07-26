"""Conversion report sidecar — pure data, no PDF logic.

Every backend populates one ConversionReport and writes it as
<stem>.report.json next to the markdown output. This gives us a
machine-readable record of what happened for each conversion:
method, page counts, OCR usage, extracted assets, quality score,
and any warnings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List


@dataclass
class ConversionReport:
    """Machine-readable record of a single conversion."""

    source: str
    output: str
    method: str
    total_pages: int = 0
    pages_with_text: int = 0
    ocr_pages: int = 0
    two_column_pages: int = 0
    extracted_assets: int = 0
    quality_score: float = 1.0
    skipped_toc_pages: int = 0
    cleaned: bool = False
    cleanup: dict = field(default_factory=dict)
    # Table fidelity signals. `table_captions_seen` counts "TABLE 9-1" /
    # "EXHIBIT 3" style captions in the output text; `tables_emitted`
    # counts grids the converter actually produced. A wide gap means the
    # captions survived but their grids collapsed into prose — the
    # failure mode a spot-check of three pages will not catch.
    tables_emitted: int = 0
    table_captions_seen: int = 0
    # Page-locator signals. `page_numbering` declares what kind of address
    # this conversion can produce: "printed" (a real page number appears
    # on the page), "pdf_only" (PDF page index only), or "none" (the
    # backend emits no locators at all). `page_printed_offset` is
    # page_printed - page_pdf, meaningful only when
    # `page_printed_offset_consistent` is True.
    page_numbering: str = "none"
    page_printed_count: int = 0
    page_locator_count: int = 0
    page_printed_coverage: float = 0.0
    page_printed_offset: int | None = None
    page_printed_offset_consistent: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def write_report(path: Path, report: ConversionReport) -> None:
    """Write a ConversionReport to a JSON sidecar at `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
