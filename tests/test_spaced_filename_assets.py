"""A space in the source filename must not break its figure references.

marker named the asset directory after the raw stem, so a source called
"A Spaced Name.pdf" produced `![](A Spaced Name_images/_page_0_Picture_0.jpeg)`.
That is not a valid CommonMark link destination — an unescaped space ends it —
and consumers stop at the first whitespace. mc-wiki's check-figures.py captures
only "A", reports the figure dangling, and the file sits on disk beside it.

Found 2026-07-29 while testing the Phase 5 pipeline, which converts whatever
lands in the inbox and so meets scanner filenames with spaces routinely. The
pymupdf4llm backend had already solved this with `safe_stem`; the marker backend
never got it.

Percent-encoding and angle-bracket wrapping are both more standards-correct and
both wrong here: the consumer resolves a ref as a literal path with no
URL-decoding, so either would still fail to find the file. Renaming the
generated directory is the only fix that needs no consumer changed.
"""
import re

import convert


def test_safe_stem_squeezes_whitespace():
    assert re.sub(r"\s+", "_", "A Spaced Name") == "A_Spaced_Name"
    assert re.sub(r"\s+", "_", "The Person and the Situation") == \
        "The_Person_and_the_Situation"


def test_unspaced_stem_is_untouched():
    """The common case must be byte-identical — this cannot rename anything."""
    for stem in ("accidental-empires", "simonton-greatness", "what-works"):
        assert re.sub(r"\s+", "_", stem) == stem


def test_a_spaced_ref_is_unreadable_by_the_consumer_pattern():
    """Why the rename is necessary, pinned as a test rather than a comment.

    This is mc-wiki's check-figures.py pattern. Against a spaced destination it
    captures a truncated path, which is why the figure reads as dangling.
    """
    img_re = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")

    spaced = "![](A Spaced Name_images/_page_0_Picture_0.jpeg)"
    assert img_re.findall(spaced) == ["A"]          # truncated → resolves to nothing

    safe = "![](A_Spaced_Name_images/_page_0_Picture_0.jpeg)"
    assert img_re.findall(safe) == ["A_Spaced_Name_images/_page_0_Picture_0.jpeg"]


def test_percent_encoding_would_not_have_helped():
    """Records why the standards-correct fix was rejected.

    The consumer does `(md.parent / ref).exists()` with no unquoting, so a
    percent-encoded destination parses cleanly and then resolves to a path that
    does not exist. Angle brackets fail earlier, on the same whitespace rule.
    """
    img_re = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")

    encoded = "![](A%20Spaced%20Name_images/x.jpeg)"
    ref = img_re.findall(encoded)[0]
    assert ref == "A%20Spaced%20Name_images/x.jpeg"
    assert "%20" in ref                    # a literal path segment, not a space

    angled = "![](<A Spaced Name_images/x.jpeg>)"
    assert img_re.findall(angled) == ["<A"]
