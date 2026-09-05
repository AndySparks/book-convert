"""Conversion report sidecar — pure data, no PDF logic.

Every backend populates one ConversionReport and writes it as
<stem>.report.json next to the markdown output. This gives us a
machine-readable record of what happened for each conversion:
method, page counts, OCR usage, extracted assets, quality score,
and any warnings.
"""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List


@dataclass
class ConversionReport:
    """Machine-readable record of a single conversion."""

    source: str
    output: str
    method: str
    source_sha256: str | None = None
    output_sha256: str | None = None
    # One entry per emitted PDF marker; method says read, interpolated or absent.
    page_map: list = field(default_factory=list)
    total_pages: int = 0
    pages_with_text: int = 0
    ocr_pages: int = 0
    two_column_pages: int = 0
    extracted_assets: int = 0
    # Asset manifest. `assets` is one entry per file this conversion wrote,
    # with the references that point at it:
    #   {"path": "Book_images/_page_64_Figure_7.jpeg",
    #    "bytes": 48213,
    #    "references": [{"target": "...", "alt": "...", "line": 812}]}
    # Paths are relative to the markdown file. A consumer relocates assets by
    # reading this list — never by pattern-matching a backend's filename
    # convention, which is a private detail that changes without notice.
    #
    # `dangling_refs_stripped` counts references to files that were not
    # written and so were removed from the markdown. The invariant is that
    # the emitted markdown has zero remaining dangling references; a non-zero
    # count here says how much the sweep had to do to get there, which is the
    # signal that extraction was off or a backend lost its assets (issue #34).
    assets: List[dict] = field(default_factory=list)
    dangling_refs_stripped: int = 0
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
    # Fraction of captured arabic folios carrying the best-supported offset.
    # None when there were too few samples to speak of support. This number was
    # always computed to decide consensus and then discarded, which left the
    # only record of it inside warning prose -- so the difference between a
    # book that renumbers once (84% support) and one whose folios are not page
    # numbers at all (3%) was unreadable by anything but a human.
    page_printed_offset_support: float | None = None
    # Heading signals. EPUB is reflowable, so `page_numbering` is always
    # "none" and headings are the *only* addressability an epub has — which
    # makes a structureless conversion otherwise indistinguishable from a
    # good one. `headings_emitted` counts markdown headings in the converted
    # body (excluding sourceconvert's own title line); `heading_source`
    # declares where they came from: "semantic" (the epub carried real
    # h1-h6), "nav" (derived from toc.ncx / the EPUB 3 nav document),
    # "class-heuristic" (derived from chapter-ish CSS classes, lower
    # confidence), or "none". Both stay None on backends that do not measure
    # them (every PDF path today) — None means "not measured", which is a
    # different claim from 0.
    headings_emitted: int | None = None
    heading_source: str | None = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=16)
def _digest(path, signature):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_report(path: Path, report: ConversionReport) -> None:
    """Write a ConversionReport to a JSON sidecar at `path`."""
    path = Path(path)
    for field_name, file_name in (("source_sha256", report.source), ("output_sha256", report.output)):
        original = Path(file_name) if file_name else None
        if original is not None and original.is_file():
            st = original.stat()
            setattr(report, field_name, _digest(str(original.resolve()),
                    (st.st_size, st.st_mtime_ns, st.st_ctime_ns)))
        else:
            setattr(report, field_name, None)
            warning = f"{field_name} unavailable: file is missing"
            if warning not in report.warnings:
                report.warnings.append(warning)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
