"""Tests for EPUB heading recovery (issue #27).

An EPUB is reflowable, so it has no page locators — headings are its only
addressability. Pandoc can only map headings the source actually carries, so
an EPUB whose chapter openers are styled `<p class="chaphead">` converts to
one flat document. These tests cover the detection, the nav-derived
fallback, the class heuristic, and the sidecar signals that make a
structureless conversion visible.

Every EPUB here is synthesized by `tests/fixtures.py` from invented text.
"""
import json
import shutil

import pytest

import convert
import epub_structure
from tests.fixtures import (
    build_epub,
    build_minimal_epub,
    build_navless_headingless_epub,
    build_semantic_epub,
    build_structureless_epub,
)

pandoc_only = pytest.mark.skipif(
    shutil.which("pandoc") is None, reason="pandoc not installed"
)


# --- detection -----------------------------------------------------------


def test_semantic_headings_detected():
    assert epub_structure.has_semantic_headings("<body><h1>Title</h1></body>")
    assert epub_structure.has_semantic_headings("<H3 class='x'>Title</H3>")


def test_headingless_markup_is_not_mistaken_for_headings():
    # `<hr/>`, `<header>`, and the literal word "h1" must not read as h1-h6.
    markup = "<body><hr/><header>x</header><p>h1 is a tag name</p></body>"
    assert not epub_structure.has_semantic_headings(markup)


def test_read_structure_finds_spine_nav_and_semantic_flag(tmp_path):
    epub = build_semantic_epub(tmp_path)
    structure = epub_structure.read_structure(epub)

    assert structure.spine == ["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"]
    assert structure.semantic is True
    assert [e.label for e in structure.nav] == [
        "The Opening Move", "The Second Move"
    ]


def test_read_structure_reports_no_semantic_headings(tmp_path):
    epub = build_navless_headingless_epub(tmp_path)
    structure = epub_structure.read_structure(epub)

    assert structure.semantic is False
    assert len(structure.spine) == 3
    assert [e.depth for e in structure.nav] == [1, 1, 2, 2]


def test_read_structure_parses_an_epub3_nav_document(tmp_path):
    epub = build_navless_headingless_epub(tmp_path, nav_style="nav")
    structure = epub_structure.read_structure(epub)

    assert structure.semantic is False
    labels = [e.label for e in structure.nav]
    assert labels == [
        "Introduction: A Broader Repertoire",
        "Part One: Foundations",
        "Chapter 1: Attention",
        "Chapter 2: Rhythm",
    ]
    # Nesting survives: the two chapters sit one level below their part.
    depths = [e.depth for e in structure.nav]
    assert depths[2] == depths[0] + 1 and depths[3] == depths[1] + 1


def test_nav_document_in_the_spine_does_not_count_as_a_semantic_heading(
    tmp_path,
):
    """An EPUB 3 nav document usually sits in the spine and usually carries
    its own `<h2>Contents</h2>`. Counting that would suppress the fallback on
    exactly the books that need it."""
    docs = [
        ("ch1.xhtml", '<p class="chaphead" id="c1">Chapter 1</p><p>x</p>'),
    ]
    epub = build_epub(
        tmp_path, docs, nav=[(1, "Chapter 1", "ch1.xhtml#c1")],
        nav_style="nav", name="navspine.epub", nav_in_spine=True,
    )
    structure = epub_structure.read_structure(epub)

    assert structure.semantic is False
    assert "OEBPS/nav.xhtml" not in structure.spine
    plan = epub_structure.plan_headings(structure)
    assert plan.source == epub_structure.SOURCE_NAV


def test_read_structure_survives_a_non_epub_file(tmp_path):
    junk = tmp_path / "not.epub"
    junk.write_bytes(b"this is not a zip")
    structure = epub_structure.read_structure(junk)
    assert structure.spine == [] and structure.nav == []


# --- nav-derived injection ----------------------------------------------


def test_nav_injection_promotes_a_matching_element_in_place(tmp_path):
    """When the anchor's element text already IS the nav label, promote it
    rather than emitting the label twice."""
    markup = (
        '<body><p class="chaphead" id="c1">Chapter 1: Attention</p>'
        "<p>Body.</p></body>"
    )
    entry = epub_structure.NavEntry(1, "Chapter 1: Attention", "d", "c1")
    out, count = epub_structure.inject_nav_headings(markup, [entry])

    assert count == 1
    assert "<h1>Chapter 1: Attention</h1>" in out
    assert 'class="chaphead"' not in out
    assert out.count("Chapter 1: Attention") == 1


def test_nav_injection_inserts_before_a_non_matching_anchor(tmp_path):
    markup = '<body><p id="c1">Some other opening line.</p></body>'
    entry = epub_structure.NavEntry(1, "Chapter 1", "d", "c1")
    out, count = epub_structure.inject_nav_headings(markup, [entry])

    assert count == 1
    assert out.index("<h1>Chapter 1</h1>") < out.index("Some other opening")
    assert "Some other opening line." in out


def test_nav_injection_hoists_an_inline_anchor_out_of_its_block(tmp_path):
    markup = '<body><p>Prose <a id="c1"/>continues here.</p></body>'
    entry = epub_structure.NavEntry(1, "Chapter 1", "d", "c1")
    out, _ = epub_structure.inject_nav_headings(markup, [entry])

    assert out.index("<h1>Chapter 1</h1>") < out.index("<p>Prose")
    # Never nested inside the paragraph.
    assert "<p>Prose <h1>" not in out


def test_nav_injection_promotes_the_block_around_an_empty_inline_anchor():
    """`<p class="chaphead"><a id="c1"/>Chapter 1</p>` — the marker is an
    empty anchor, but the paragraph around it IS the title. Promote the
    paragraph rather than emitting the label twice."""
    markup = (
        '<body><p class="chaphead"><a id="c1"/>Chapter 1: Attention</p>'
        "<p>Body.</p></body>"
    )
    entry = epub_structure.NavEntry(1, "Chapter 1: Attention", "d", "c1")
    out, count = epub_structure.inject_nav_headings(markup, [entry])

    assert count == 1
    assert "<h1>Chapter 1: Attention</h1>" in out
    assert out.count("Chapter 1: Attention") == 1
    assert "chaphead" not in out


def test_nav_injection_falls_back_to_the_body_start_without_an_anchor(tmp_path):
    markup = "<body><p>Opening line.</p></body>"
    entry = epub_structure.NavEntry(1, "Chapter 1", "d", None)
    out, count = epub_structure.inject_nav_headings(markup, [entry])

    assert count == 1
    assert out.startswith("<body><h1>Chapter 1</h1>")


def test_nav_injection_maps_nesting_to_heading_depth(tmp_path):
    markup = '<body><p id="a">A</p><p id="b">B</p></body>'
    entries = [
        epub_structure.NavEntry(1, "Part", "d", "a"),
        epub_structure.NavEntry(2, "Chapter", "d", "b"),
    ]
    out, _ = epub_structure.inject_nav_headings(markup, entries, min_depth=1)
    assert "<h1>Part</h1>" in out and "<h2>Chapter</h2>" in out


def test_nav_injection_escapes_label_markup(tmp_path):
    markup = "<body><p>x</p></body>"
    entry = epub_structure.NavEntry(1, "Ben & Jerry <inc>", "d", None)
    out, _ = epub_structure.inject_nav_headings(markup, [entry])
    assert "<h1>Ben &amp; Jerry &lt;inc&gt;</h1>" in out


def test_plan_prefers_nav_over_the_class_heuristic(tmp_path):
    epub = build_navless_headingless_epub(tmp_path)
    plan = epub_structure.plan_headings(epub_structure.read_structure(epub))

    assert plan.source == epub_structure.SOURCE_NAV
    assert plan.injected == 4


def test_plan_reports_semantic_and_rewrites_nothing(tmp_path):
    epub = build_semantic_epub(tmp_path)
    plan = epub_structure.plan_headings(epub_structure.read_structure(epub))

    assert plan.source == epub_structure.SOURCE_SEMANTIC
    assert plan.replacements == {}


# --- class heuristic -----------------------------------------------------


def test_class_heuristic_picks_a_chapterish_class(tmp_path):
    docs = {"a": '<p class="chaphead">Chapter 1</p><p class="bodytext">x</p>'}
    assert epub_structure.pick_heuristic_class(docs) == "chaphead"


def test_class_heuristic_ignores_ordinary_body_classes(tmp_path):
    docs = {"a": '<p class="bodytext">x</p><p class="indent">y</p>'}
    assert epub_structure.pick_heuristic_class(docs) is None


def test_class_heuristic_skips_long_paragraphs(tmp_path):
    long_text = "word " * 60
    docs = {"a": '<p class="chaphead">%s</p>' % long_text}
    assert epub_structure.pick_heuristic_class(docs) is None


def test_class_heuristic_injection_promotes_only_the_chosen_class(tmp_path):
    markup = (
        '<body><p class="chaphead">Chapter 1</p>'
        '<p class="bodytext">Chapter 1 begins here.</p></body>'
    )
    out, count = epub_structure.inject_class_headings(markup, "chaphead")
    assert count == 1
    assert "<h1>Chapter 1</h1>" in out
    assert '<p class="bodytext">Chapter 1 begins here.</p>' in out


def test_plan_falls_back_to_the_class_heuristic_without_a_nav(tmp_path):
    epub = build_structureless_epub(tmp_path, chapterish=True)
    plan = epub_structure.plan_headings(epub_structure.read_structure(epub))

    assert plan.source == epub_structure.SOURCE_CLASS
    assert plan.injected == 2


def test_plan_gives_up_honestly_when_there_is_no_signal(tmp_path):
    epub = build_structureless_epub(tmp_path, chapterish=False)
    plan = epub_structure.plan_headings(epub_structure.read_structure(epub))

    assert plan.source == epub_structure.SOURCE_NONE
    assert plan.injected == 0
    assert plan.replacements == {}


# --- heading counting ----------------------------------------------------


def test_count_markdown_headings():
    body = "# One\n\ntext\n\n### Three\n\n#nospace\n"
    assert epub_structure.count_markdown_headings(body) == 2


def test_count_markdown_headings_ignores_fenced_code():
    body = "# One\n\n```\n# not a heading\n```\n\n## Two\n"
    assert epub_structure.count_markdown_headings(body) == 2


# --- rewriting -----------------------------------------------------------


def test_rewrite_epub_keeps_mimetype_first_and_stored(tmp_path):
    import zipfile

    src = build_semantic_epub(tmp_path)
    dest = tmp_path / "rewritten.epub"
    epub_structure.rewrite_epub(src, dest, {"OEBPS/ch1.xhtml": "<html/>"})

    with zipfile.ZipFile(dest) as zf:
        infos = zf.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert zf.read("OEBPS/ch1.xhtml").decode() == "<html/>"
        # Untouched entries survive byte-for-byte.
        with zipfile.ZipFile(src) as orig:
            assert zf.read("OEBPS/ch2.xhtml") == orig.read("OEBPS/ch2.xhtml")


def test_prepare_epub_leaves_a_semantic_book_untouched(tmp_path):
    epub = build_semantic_epub(tmp_path)
    work = tmp_path / "work"
    path, source, injected = epub_structure.prepare_epub(epub, work)

    assert path == epub
    assert source == epub_structure.SOURCE_SEMANTIC
    assert injected == 0
    assert not work.exists()


def test_prepare_epub_rewrites_a_headingless_book(tmp_path):
    epub = build_navless_headingless_epub(tmp_path)
    before = epub.read_bytes()
    work = tmp_path / "work"
    path, source, injected = epub_structure.prepare_epub(epub, work)

    assert path != epub
    assert source == epub_structure.SOURCE_NAV
    assert injected == 4
    assert epub.read_bytes() == before        # source is never mutated


# --- end-to-end through pandoc ------------------------------------------


def _sidecar(output_dir, stem):
    return json.loads(
        (output_dir / f"{stem}.report.json").read_text(encoding="utf-8")
    )


@pandoc_only
def test_semantic_epub_converts_unchanged_and_reports_semantic(tmp_path):
    """(a) The normal path must not regress."""
    epub = build_semantic_epub(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pandoc(epub, out_dir)
    text = (out_dir / "semantic.md").read_text(encoding="utf-8")

    assert report.heading_source == epub_structure.SOURCE_SEMANTIC
    assert report.headings_emitted == 2
    assert "# The Opening Move" in text
    assert "# The Second Move" in text
    assert "A manager decides what the team will not do." in text
    assert report.warnings == []

    data = _sidecar(out_dir, "semantic")
    assert data["heading_source"] == "semantic"
    assert data["headings_emitted"] == 2
    assert data["page_numbering"] == "none"


@pandoc_only
@pytest.mark.parametrize("nav_style", ["ncx", "nav"])
def test_headingless_epub_recovers_headings_from_the_nav(tmp_path, nav_style):
    """(b) Zero h1-h6 plus a good nav must yield headings, sourced `nav`."""
    epub = build_navless_headingless_epub(
        tmp_path, name=f"{nav_style}.epub", nav_style=nav_style
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pandoc(epub, out_dir)
    text = (out_dir / f"{nav_style}.md").read_text(encoding="utf-8")

    assert report.heading_source == epub_structure.SOURCE_NAV
    assert report.headings_emitted == 4
    assert "# Introduction: A Broader Repertoire" in text
    assert "# Part One: Foundations" in text
    # Nav nesting became heading depth.
    assert "## Chapter 1: Attention" in text
    assert "## Chapter 2: Rhythm" in text
    # The body text still made it through.
    assert "Where a manager looks is where the team looks." in text
    # And the operator is told the headings were derived, not native.
    assert any("no semantic h1-h6" in w for w in report.warnings)


@pandoc_only
def test_headingless_epub_without_a_nav_uses_the_class_heuristic(tmp_path):
    """(c-1) No nav, but recognizable chapter classes."""
    epub = build_structureless_epub(
        tmp_path, name="heur.epub", chapterish=True
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pandoc(epub, out_dir)
    text = (out_dir / "heur.md").read_text(encoding="utf-8")

    assert report.heading_source == epub_structure.SOURCE_CLASS
    assert report.headings_emitted == 2
    assert "# Chapter 1: The Flat Book" in text
    assert "# Chapter 2: Still Flat" in text


@pandoc_only
def test_epub_with_no_signal_at_all_converts_and_says_so(tmp_path):
    """(c-2) Nothing to recover: convert anyway, report `none`, warn loudly."""
    epub = build_structureless_epub(
        tmp_path, name="flat.epub", chapterish=False
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pandoc(epub, out_dir)
    text = (out_dir / "flat.md").read_text(encoding="utf-8")

    assert report.heading_source == epub_structure.SOURCE_NONE
    assert report.headings_emitted == 0
    # Body text still converts — we degrade, we do not fail.
    assert "Nothing here announces itself as a heading." in text
    assert any("no structural addressing" in w for w in report.warnings)

    data = _sidecar(out_dir, "flat")
    assert data["heading_source"] == "none"
    assert data["headings_emitted"] == 0


@pandoc_only
def test_a_contradictory_sidecar_is_reconciled_not_published(
    tmp_path, monkeypatch
):
    """If our spine analysis learns nothing (exotic container) but pandoc
    still emits headings, they came from the source. Publishing
    `heading_source: none` over a structured output would be the same silent
    lie in the other direction."""
    epub = build_semantic_epub(tmp_path, name="exotic.epub")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setattr(
        epub_structure, "prepare_epub",
        lambda path, work: (path, epub_structure.SOURCE_NONE, 0),
    )
    report = convert.convert_with_pandoc(epub, out_dir)

    assert report.headings_emitted == 2
    assert report.heading_source == epub_structure.SOURCE_SEMANTIC
    assert report.warnings == []


@pandoc_only
def test_a_failed_heading_analysis_never_loses_the_book(tmp_path, monkeypatch):
    """The analysis is a nice-to-have; the conversion is not. An exception
    inside it must degrade to the plain pandoc path."""
    epub = build_semantic_epub(tmp_path, name="boom.epub")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def explode(path, work):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(epub_structure, "prepare_epub", explode)
    report = convert.convert_with_pandoc(epub, out_dir)

    assert "# The Opening Move" in (out_dir / "boom.md").read_text()
    assert report.headings_emitted == 2


@pandoc_only
def test_minimal_epub_fixture_still_reports_semantic(tmp_path):
    """The pre-existing smoke fixture carries a real <h1>; it must not
    change behaviour under the new path."""
    epub = build_minimal_epub(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pandoc(epub, out_dir)
    assert report.heading_source == epub_structure.SOURCE_SEMANTIC
    assert report.headings_emitted == 1


@pandoc_only
def test_a_single_doc_epub_with_many_nav_anchors(tmp_path):
    """All chapters in one XHTML file — the flat-spine shape, where every
    insertion offset lands in the same document."""
    body = "".join(
        '<p class="chaphead" id="c%d">Chapter %d</p><p>Body %d.</p>'
        % (i, i, i)
        for i in range(1, 6)
    )
    epub = build_epub(
        tmp_path,
        docs=[("all.xhtml", body)],
        nav=[(1, "Chapter %d" % i, "all.xhtml#c%d" % i) for i in range(1, 6)],
        nav_style="ncx",
        name="single.epub",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = convert.convert_with_pandoc(epub, out_dir)
    text = (out_dir / "single.md").read_text(encoding="utf-8")

    assert report.heading_source == epub_structure.SOURCE_NAV
    assert report.headings_emitted == 5
    # Order is preserved.
    positions = [text.index("# Chapter %d" % i) for i in range(1, 6)]
    assert positions == sorted(positions)
