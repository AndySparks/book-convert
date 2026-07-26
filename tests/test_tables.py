"""Tests for table detection and grid reconstruction.

PyMuPDF extracts borderless tables column-by-column, producing a flat
vertical stream of one-cell-per-line text. The helpers exercised here
rebuild a proper grid from the dict-level line coordinates so markdown
tables land in the output rather than a scrambled dump of cells.
"""
import re

import convert
from report import ConversionReport


# --- _cluster_1d ---


def test_cluster_1d_merges_nearby_values():
    """Values with gaps smaller than tol collapse into one cluster center."""
    centers = convert._cluster_1d([75.0, 76.0, 150.0, 151.0, 300.0], tol=10)
    assert len(centers) == 3
    assert centers[0] == (75.0 + 76.0) / 2
    assert centers[1] == (150.0 + 151.0) / 2
    assert centers[2] == 300.0


def test_cluster_1d_empty():
    assert convert._cluster_1d([], tol=10) == []


def test_cluster_1d_all_apart():
    """Values all beyond tol each form their own cluster."""
    assert convert._cluster_1d([10, 100, 200, 300], tol=10) == [10, 100, 200, 300]


# --- _cluster_lines_to_rows ---


def test_cluster_lines_to_rows_groups_by_y_tolerance():
    """Lines within y_tol land in the same visual row, sorted left-to-right."""
    lines = [
        (100.0, 75.0, "Henry"),
        (100.5, 200.0, "Singleton"),  # same row as Henry
        (120.0, 75.0, "Warren"),      # next row
        (120.0, 200.0, "Buffett"),
    ]
    rows = convert._cluster_lines_to_rows(lines, y_tol=3)
    assert len(rows) == 2
    assert [e[2] for e in rows[0]] == ["Henry", "Singleton"]
    assert [e[2] for e in rows[1]] == ["Warren", "Buffett"]


def test_cluster_lines_to_rows_empty():
    assert convert._cluster_lines_to_rows([], y_tol=3) == []


# --- _row_looks_like_prose ---


def test_row_prose_single_long_line_at_left_margin():
    """A full-width paragraph line starting at the left margin reads as prose."""
    row = [(100.0, 72.0, "The outsider CEOs were master delegators running highly decentralized organizations.")]
    assert convert._row_looks_like_prose(row, page_width=540) is True


def test_row_prose_rejects_multi_cell_row():
    """Multi-cell rows are never prose, even when the joined text reads like a sentence."""
    row = [
        (100.0, 75.0, "Experience"),
        (100.0, 168.0, "First-time CEOs with little prior managerial experience"),
        (100.0, 356.0, "Experienced managers with Gladwell's 10,000 hours"),
    ]
    # Three separate cells on one visual row — not prose, even though
    # the joined string has 18 tokens and many lowercase words.
    assert convert._row_looks_like_prose(row, page_width=540) is False


def test_row_prose_rejects_symbol_row():
    """Rows packed with symbols (checkmarks, single letters) are not prose."""
    row = [(100.0, 75.0, "Henry \u221a No \u221a \u221a \u221a No Teledyne return H")]
    assert convert._row_looks_like_prose(row, page_width=540) is False


def test_row_prose_rejects_short_row():
    """Short lines (fewer than 8 tokens) never count as prose."""
    row = [(100.0, 72.0, "A shared worldview")]
    assert convert._row_looks_like_prose(row, page_width=540) is False


def test_row_prose_rejects_indented_line():
    """A long line that starts past the left margin is not a paragraph start."""
    row = [(100.0, 200.0, "the stock price rose nearly twenty percent overnight after the announcement")]
    assert convert._row_looks_like_prose(row, page_width=540) is False


# --- _row_is_decorative ---


def test_row_is_decorative_dots():
    assert convert._row_is_decorative([(100.0, 297.0, ". . .")]) is True


def test_row_is_decorative_rejects_alphanumeric():
    assert convert._row_is_decorative([(100.0, 75.0, "Hedgehog")]) is False


# --- _TABLE_CAPTION_RE ---


def test_table_caption_matches_common_forms():
    assert convert._TABLE_CAPTION_RE.match("TABLE 9-1")
    assert convert._TABLE_CAPTION_RE.match("TABLE 9.1")
    assert convert._TABLE_CAPTION_RE.match("Table 12-3")
    assert convert._TABLE_CAPTION_RE.match("  TABLE 9-1  ")


def test_table_caption_rejects_non_caption_lines():
    assert not convert._TABLE_CAPTION_RE.match("Table of Contents")
    assert not convert._TABLE_CAPTION_RE.match("as table 9-1 shows")
    assert not convert._TABLE_CAPTION_RE.match("TABLE")


# --- _build_markdown_table ---


def _cells_to_row(cells, y):
    """Build a dict-level visual row from (x, text) tuples at a given y."""
    return [(float(y), float(x), text) for x, text in cells]


def test_build_markdown_table_three_column_grid():
    """A clean 3-column / 3-row grid produces a valid markdown table."""
    visual_rows = [
        _cells_to_row([(75, "Label"), (200, "Outsider"), (400, "Peer")], y=100),
        _cells_to_row([(75, "Experience"), (200, "First-time"), (400, "Experienced")], y=120),
        _cells_to_row([(75, "Objective"), (200, "Long-term value"), (400, "Growth")], y=140),
    ]
    md = convert._build_markdown_table(visual_rows, caption="TABLE 1-1", subtitle="Profile")
    assert md is not None
    assert "**TABLE 1-1 — Profile**" in md
    assert "| Label | Outsider | Peer |" in md
    assert "| Experience | First-time | Experienced |" in md
    assert "| Objective | Long-term value | Growth |" in md
    # Header separator line
    assert re.search(r"\|---\|---\|---\|", md)


def test_build_markdown_table_merges_continuation_rows():
    """Sparse rows that only fill a single column fold upward into the previous row."""
    visual_rows = [
        _cells_to_row(
            [(75, "Henry"), (129, "\u221a"), (151, "No"), (463, "Teledyne")],
            y=100,
        ),
        _cells_to_row([(75, "Singleton")], y=110),  # CEO name wraps
        _cells_to_row(
            [(75, "Warren"), (129, "\u221a"), (151, "No"), (463, "Float")],
            y=130,
        ),
    ]
    md = convert._build_markdown_table(visual_rows, "TABLE 9-1", None)
    assert md is not None
    assert "Henry Singleton" in md
    assert "Warren" in md
    # After merging, the table has 2 logical rows: "Henry Singleton" (used
    # as the header) and "Warren". Markdown output is header + separator
    # + 1 data row = 3 pipe-lines.
    lines = [l for l in md.split("\n") if l.startswith("|")]
    assert len(lines) == 3


def test_build_markdown_table_rejects_single_column():
    """A region that collapses into a single column is not a real table."""
    visual_rows = [
        _cells_to_row([(75, "one")], y=100),
        _cells_to_row([(75, "two")], y=120),
        _cells_to_row([(75, "three")], y=140),
    ]
    assert convert._build_markdown_table(visual_rows, "TABLE 1-1", None) is None


def test_build_markdown_table_rejects_too_few_rows():
    visual_rows = [
        _cells_to_row([(75, "Label"), (200, "Value")], y=100),
    ]
    assert convert._build_markdown_table(visual_rows, "TABLE 1-1", None) is None


# --- _merge_continuation_rows ---


def test_merge_continuation_rows_folds_sparse_below_dense():
    """A sparse row immediately after a dense row is merged into the dense row."""
    grid = [
        ["Henry", "\u221a", "No", "Teledyne"],
        ["Singleton", "", "", ""],
        ["Warren", "\u221a", "No", "Float"],
    ]
    merged = convert._merge_continuation_rows(grid)
    assert merged == [
        ["Henry Singleton", "\u221a", "No", "Teledyne"],
        ["Warren", "\u221a", "No", "Float"],
    ]


def test_merge_continuation_rows_preserves_dense_rows():
    """Consecutive dense rows are never merged."""
    grid = [
        ["a", "b", "c"],
        ["d", "e", "f"],
        ["g", "h", "i"],
    ]
    assert convert._merge_continuation_rows(grid) == grid


def test_merge_continuation_rows_empty():
    assert convert._merge_continuation_rows([]) == []


# --- _extract_page_text_with_regions ---


def test_extract_page_text_with_regions_matches_legacy_table_path(tmp_path):
    """With only table regions, the new function matches the old behavior.

    We build a tiny PDF whose first page has a one-line caption + prose,
    and pass a table region list to _extract_page_text_with_regions. The
    output should contain the markdown region and the surrounding prose.
    """
    import fitz

    from tests import fixtures

    pdf = fixtures.build_text_pdf(tmp_path, pages=1, body="Surrounding prose line.")
    with fitz.open(str(pdf)) as doc:
        page = doc[0]
        # Fake table region in the middle of the page.
        rect_md = "**TABLE 1** | a | b |\n|---|---|\n| 1 | 2 |"
        regions = [(200.0, 260.0, rect_md)]
        result = convert._extract_page_text_with_regions(page, regions)
    assert "Surrounding prose line" in result
    assert "| a | b |" in result


# --- count_table_signals / apply_table_signals ---------------------------
#
# These back the `tables_emitted` / `table_captions_seen` sidecar fields.
# The gap between the two is the only cheap signal that a book's grids
# collapsed into prose, so the counts have to be right on real-world
# caption shapes (bold, appendix letters, EXHIBIT) and must not be fooled
# by prose that merely mentions a table.


def test_count_table_signals_counts_gfm_grid_and_caption():
    md = "TABLE A-16 Mean Motive Levels\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    assert convert.count_table_signals(md) == (1, 1)


def test_count_table_signals_matches_bold_and_exhibit_captions():
    md = "**TABLE 3.2.** Some Events\n\ntext\n\nEXHIBIT 5-1 Another\n"
    emitted, captions = convert.count_table_signals(md)
    assert captions == 2
    assert emitted == 0


def test_count_table_signals_counts_html_tables():
    md = "TABLE 1 x\n\n<table><tbody><tr><td>a</td></tr></tbody></table>\n"
    assert convert.count_table_signals(md) == (1, 1)


def test_count_table_signals_ignores_prose_mentions_of_tables():
    md = "As Table 3.2 shows, the effect held. See the table above.\n"
    assert convert.count_table_signals(md) == (0, 0)


def test_apply_table_signals_warns_when_captions_outnumber_grids(tmp_path):
    """The collapsed-grid case: captions survive, grids don't."""
    md = tmp_path / "out.md"
    md.write_text("TABLE 1 a\n\nTABLE 2 b\n\n| x |\n|---|\n| 1 |\n", encoding="utf-8")
    report = ConversionReport(source="s.pdf", output=str(md), method="marker")
    convert.apply_table_signals(report, md)
    assert (report.table_captions_seen, report.tables_emitted) == (2, 1)
    assert any("collapsed into prose" in w for w in report.warnings)


def test_apply_table_signals_silent_when_grids_match_captions(tmp_path):
    md = tmp_path / "out.md"
    md.write_text("TABLE 1 a\n\n| x |\n|---|\n| 1 |\n", encoding="utf-8")
    report = ConversionReport(source="s.pdf", output=str(md), method="marker")
    convert.apply_table_signals(report, md)
    assert report.warnings == []


def test_apply_table_signals_survives_unreadable_output(tmp_path):
    report = ConversionReport(source="s.pdf", output="nope.md", method="marker")
    convert.apply_table_signals(report, tmp_path / "does-not-exist.md")
    assert report.tables_emitted == 0
    assert any("could not count tables" in w for w in report.warnings)
