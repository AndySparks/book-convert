"""Tests for heading promotion and list-page preservation."""
import convert


# --- _looks_like_list_page ---

INDEX_PAGE = """\
Apollo Program
Apple, 4.1, 5.1, 5.2, 6.1, 14.1
branding of
monopoly profits of
Aristotle
Army Corps of Engineers
AT&T
Aztecs
Baby Boomers
Bacon, Francis
Bangladesh
Barnes & Noble
Beijing
Bell Labs
Berlin Wall
"""

INDEX_PAGE_WITH_SUBENTRIES = """\
valuing of
company culture
Compaq
compensation
competition, 3.1, 5.1, 13.1, bm1.1
and capitalism, 3.1, 8.1
ideology of
imitative
lies of
as relic of history
ruthlessness in
as war
complacency
complementarity
substitution vs.
technology and
compound interest
"""

PROSE_PAGE = """\
The organization's leadership must consider the behavior of employees
across every department. A manager who understands the people on the
team can build trust through clear communication. Performance improves
when workers feel their contributions are recognized and their ideas
are taken seriously by the executives. This principle appears in every
major study of management practice over the past fifty years, from the
earliest research on motivation to contemporary work on psychological
safety and team effectiveness. Organizations that ignore it pay a cost
in turnover, engagement, and productivity.
"""

SHORT_INDEX_TAIL = """\
White, Phil
Wiles, Andrew
Wilson, Andrew
Winehouse, Amy
World Wide Web
Xanadu
X.com
Yahoo!, 2.1, 3.1, 3.2, 5.1, 6.1
Yammer
Yelp
YouTube, 10.1, 12.1
ZocDoc
Zuckerberg, Mark, prf.1, 5.1, 6.1, 14.1
Zynga
"""


def test_looks_like_list_page_classic_index():
    assert convert._looks_like_list_page(INDEX_PAGE) is True


def test_looks_like_list_page_with_subentries():
    """Index pages where sub-entries start with 'and', 'as', etc. still detect."""
    assert convert._looks_like_list_page(INDEX_PAGE_WITH_SUBENTRIES) is True


def test_looks_like_list_page_short_tail():
    """Short final index pages (W-Z range, ~14 entries) still detect."""
    assert convert._looks_like_list_page(SHORT_INDEX_TAIL) is True


def test_looks_like_list_page_rejects_prose():
    """Wrapped prose paragraphs are not mistaken for lists."""
    assert convert._looks_like_list_page(PROSE_PAGE * 3) is False


def test_looks_like_list_page_empty():
    assert convert._looks_like_list_page("") is False
    assert convert._looks_like_list_page("\n\n\n") is False


# --- _merge_split_caps_headings ---


def test_merge_split_caps_headings_four_line_title():
    """Chapter title extracted as one-word-per-line merges into single line."""
    lines = [
        "",
        "THE",
        "CHALLENGE",
        "OF THE",
        "FUTURE",
        "WHENEVER I INTERVIEW someone for a job",
    ]
    result = convert._merge_split_caps_headings(lines)
    assert "THE CHALLENGE OF THE FUTURE" in result
    # Merged line should replace the 4 fragments
    assert "THE" not in [r.strip() for r in result if r.strip()]


def test_merge_split_caps_headings_two_line_section():
    """Sub-section headings like 'THE' + 'CASE FOR SECRETS' merge."""
    lines = [
        "HP build them.",
        "THE",
        "CASE FOR SECRETS",
        "You can't find secrets without looking for them.",
    ]
    result = convert._merge_split_caps_headings(lines)
    assert "THE CASE FOR SECRETS" in result


def test_merge_split_caps_headings_leaves_singles():
    """Lone all-caps line is not merged with unrelated text."""
    lines = ["Regular body text.", "FOUNDATIONS", "EVERY GREAT COMPANY is unique."]
    result = convert._merge_split_caps_headings(lines)
    assert "FOUNDATIONS" in result
    # Not merged with "EVERY GREAT..." since that's body text (mixed case)
    assert not any("FOUNDATIONS EVERY" in line for line in result)


# --- _promote_bookmark_headings ---


def test_promote_bookmark_headings_multiline_split():
    """Bookmark title split across multiple lines gets promoted to ##."""
    text = (
        "<!-- Page 10 -->\n"
        "\n"
        "THE CHALLENGE OF THE FUTURE\n"
        "WHENEVER I INTERVIEW someone for a job\n"
    )
    titles = ["1. The Challenge of the Future"]
    result = convert._promote_bookmark_headings(text, titles)
    assert "## THE CHALLENGE OF THE FUTURE" in result
    assert "WHENEVER I INTERVIEW" in result


def test_promote_bookmark_headings_inline_prefix():
    """Bookmark title jammed into the first paragraph line is split out."""
    text = (
        "<!-- Page 19 -->\n"
        "\n"
        "PARTY LIKE IT'S 1999 OUR CONTRARIAN QUESTION—What important truth do very few people agree with you on?\n"
    )
    titles = ["2. Party Like It's 1999"]
    result = convert._promote_bookmark_headings(text, titles)
    assert "## PARTY LIKE IT'S 1999" in result
    assert "OUR CONTRARIAN QUESTION" in result
    # The body text must still be present, just on a new line
    assert "What important truth" in result


def test_promote_bookmark_headings_word_boundary():
    """Match that would bisect a real word is rejected."""
    text = "Copyrighted material here under license.\n"
    titles = ["Copyright"]
    result = convert._promote_bookmark_headings(text, titles)
    # Should NOT promote since the match would split "Copyrighted"
    assert "## Copyright" not in result
    assert "Copyrighted material" in result


def test_promote_bookmark_headings_no_titles():
    text = "Some body text.\n"
    assert convert._promote_bookmark_headings(text, []) == text


def test_promote_bookmark_headings_strips_chapter_numeral():
    """Bookmark titles like '9. Foundations' strip the leading '9. ' before matching."""
    text = "FOUNDATIONS\nEVERY GREAT COMPANY is unique\n"
    result = convert._promote_bookmark_headings(text, ["9. Foundations"])
    assert "## FOUNDATIONS" in result


# --- Integration: _format_headings picks up merged caps ---


def test_format_headings_promotes_merged_split_caps():
    """After _merge_split_caps_headings runs, the merged heading is promoted."""
    text = "\nTHE\nCHALLENGE\nOF THE\nFUTURE\nWHENEVER I INTERVIEW someone\n"
    result = convert._format_headings(text)
    assert "## THE CHALLENGE OF THE FUTURE" in result or "### THE CHALLENGE OF THE FUTURE" in result
