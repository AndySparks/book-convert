"""Tests for the post-conversion cleanup pass (cleanup.clean_markdown).

The de-join assertions require pyspellchecker; they skip if it is absent.
The dictionary-free repairs (stray consonants, picture-text) always run.
"""
import pytest

import cleanup


def _has_speller():
    return cleanup._speller() is not None


needs_dict = pytest.mark.skipif(
    not _has_speller(), reason="pyspellchecker not installed"
)


# --- de-join: restores dropped spaces at function-word boundaries ------------

@needs_dict
@pytest.mark.parametrize("joined,expected", [
    ("sucha", "such a"),
    ("thefrozen", "the frozen"),
    ("ofwater", "of water"),
    ("havea", "have a"),
    ("makea", "make a"),
    ("awayfrom", "away from"),
    ("hisface", "his face"),
    ("ofthe", "of the"),
])
def test_dejoin_splits_function_word_joins(joined, expected):
    out, stats = cleanup.clean_markdown(f"the cat sat {joined} chair here.")
    assert expected in out
    assert stats["function_word_joins"] >= 1


# --- guards: never split a legitimate single word ----------------------------

@needs_dict
@pytest.mark.parametrize("word", [
    "colour",     # British spelling pyspellchecker rejects
    "humour",
    "ardour",
    "aeroplane",  # no function-word split point
    "moocow",     # Joyce coinage inside a quote
    "manservants",
    "givenness",  # linguistics coinage
    "nonfinite",
    "attaches",   # common word pyspellchecker misses; "at" excluded as leading
])
def test_dejoin_preserves_real_words(word):
    text = f"A sentence containing {word} in the middle."
    out, _ = cleanup.clean_markdown(text)
    assert word in out, f"{word!r} was wrongly split"


@needs_dict
def test_dejoin_preserves_short_stem_proper_noun():
    # "Iowa" mis-OCR'd as "lowa" must not become "low a" (short content stem
    # + trailing "a"). "have a"/"from a" (>=4 stem) still split fine.
    out, _ = cleanup.clean_markdown("published in lowa City that year")
    assert "low a" not in out
    out2, _ = cleanup.clean_markdown("they havea plan away froma town")
    assert "have a" in out2 and "from a" in out2


@needs_dict
def test_dejoin_preserves_offate_ambiguous():
    # "off" is excluded as a leading function word, so "offate" is left intact
    # rather than guessed as "off ate" (real reading is "of fate").
    out, _ = cleanup.clean_markdown("three uses offate here")
    assert "off ate" not in out


# --- stray-consonant citation ghosts (no dictionary needed) ------------------

@pytest.mark.parametrize("bad,good", [
    ("—wWilliam Golding", "—William Golding"),
    ("tThe Journals", "The Journals"),
    ("lIsaiah Berlin", "Isaiah Berlin"),
])
def test_stray_consonant_fix(bad, good):
    out, stats = cleanup.clean_markdown(bad)
    assert good in out
    assert stats["stray_consonant_fixes"] >= 1


def test_stray_consonant_leaves_real_words():
    # "a"/"i" are real words and must not be stripped; normal capitalised
    # words with no glued consonant are untouched.
    text = "a Wonderful The Xylophone"
    out, stats = cleanup.clean_markdown(text)
    assert out.strip() == text
    assert stats["stray_consonant_fixes"] == 0


# --- picture-text blocks -----------------------------------------------------

def _pic(inner):
    return (
        "**----- Start of picture text -----**<br>\n"
        f"{inner}\n"
        "**----- End of picture text -----**<br>"
    )


def test_picture_text_toc_is_unwrapped_and_kept():
    toc = "|Chapter|1|Short Sentences|9|\n|Index of Terms|301|"
    text = f"intro\n\n{_pic(toc)}\n\nbody"
    out, stats = cleanup.clean_markdown(text)
    assert "Index of Terms" in out          # content kept
    assert "picture text" not in out         # wrapper removed
    assert stats["toc_blocks_unwrapped"] == 1
    assert stats["garble_blocks_removed"] == 0


def test_picture_text_garble_is_dropped():
    text = f"body\n\n{_pic('ISBN 0-9b1392)-8-5<br>eg ee J > 2')}\n\nmore"
    out, stats = cleanup.clean_markdown(text)
    assert "ISBN" not in out
    assert "picture text" not in out
    assert stats["garble_blocks_removed"] == 1
    assert stats["toc_blocks_unwrapped"] == 0


# --- idempotency -------------------------------------------------------------

def test_clean_is_idempotent():
    text = (
        "The catsat onthe mat. —wWilliam Blake\n\n"
        + _pic("ISBN 123<br>garble") + "\n\n"
        + _pic("|Index of Terms|1|")
    )
    once, _ = cleanup.clean_markdown(text)
    twice, stats2 = cleanup.clean_markdown(once)
    assert once == twice
    assert stats2["garble_blocks_removed"] == 0  # nothing left to remove


def test_clean_returns_stats_shape():
    _, stats = cleanup.clean_markdown("plain text with no artifacts")
    for key in ("function_word_joins", "stray_consonant_fixes",
                "toc_blocks_unwrapped", "garble_blocks_removed",
                "dejoin_available"):
        assert key in stats
