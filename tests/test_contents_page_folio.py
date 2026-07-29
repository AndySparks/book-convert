"""A contents or index page must not yield a listed page number as its folio.

Such a page carries several lines shaped exactly like a folio that are not
one. Capture used to prefer any bare folio-shaped line over a folio embedded
in a running head, which is right on an ordinary page and backwards here.

Real case: Bohnet's *What Works* (ingested 2026-07-29). Its five contents
sheets emitted page_printed 1, 44, 123, 266 and 285 where the printed folios
are roman. Five adjacent bad captures then defeated offset derivation for the
whole book, so nothing downstream could interpolate either.
"""
import convert


HEAD = {"viii Contents", "Contents"}


def _strip(page_text, header=HEAD, footer=frozenset()):
    return convert._strip_marker_page_furniture(page_text, header, footer)


# --- the regression itself -------------------------------------------------

def test_contents_page_does_not_emit_a_listed_number_as_the_folio():
    """What Works sheet 7, verbatim in shape.

    The band holds the real folio (roman, in the running head) and a listed
    number. Before the fix this emitted `44`.

    It does not recover `viii`, and that is deliberate. The embedded-folio
    regexes match arabic only, and widening them to roman is not free: the
    roman grammar is a letter-bag that also matches English words, so
    `I Introduction` or `Civil War` in a running head would start producing
    folios. That enhancement carries its own false-positive risk and belongs
    in its own change. Here the harm is a confident wrong number, and the
    fix is to stop emitting one.
    """
    page = (
        "viii Contents\n"
        "\n"
        "# 2. De-Biasing Minds Is Hard\n"
        "\n"
        "44\n"
        "\n"
        "How to know when to settle; self-serving bias; halos and hindsight\n"
        "\n"
        "#### 3. Doing It Yourself Is Risky\n"
        "\n"
        "62\n"
    )
    folio, _body = _strip(page)
    assert folio != "44"
    assert folio is None


def test_arabic_running_head_folio_still_wins_on_a_contents_page():
    """Where the running head folio IS capturable, it must be preferred.

    This is the path the suppression falls through to, so it needs a test
    that does not depend on the roman gap above.
    """
    page = (
        "108 Contents\n"
        "\n"
        "# 2. De-Biasing Minds Is Hard\n"
        "\n"
        "44\n"
        "\n"
        "How to know when to settle; self-serving bias\n"
        "\n"
        "#### 3. Doing It Yourself Is Risky\n"
        "\n"
        "62\n"
    )
    folio, _body = _strip(page, header={"Contents"})
    assert folio == "108"


def test_rule_needs_a_plurality_of_listed_numbers():
    """The discriminator is plurality, and the limit is worth stating.

    A contents page listing exactly one entry still looks like an ordinary
    page carrying one folio, and is still mis-captured. Real contents pages
    list many -- What Works' had four apiece -- so this is a residual, not the
    observed failure. Recorded as a test so it is a known edge rather than a
    surprise.
    """
    page = "# 6. Orchestrating Smarter Evaluation Procedures\n\n123\n\nPink is for tax bills\n"
    folio, _body = _strip(page, header=frozenset())
    assert folio == "123"      # not yet distinguishable from a real folio


def test_contents_page_with_no_running_head_captures_nothing():
    """What Works sheet 8: no running head survived, several listed numbers.

    There is nothing trustworthy to capture, so capture nothing and let
    interpolation fill it. A gap is honest; 123 would be a confident lie.
    """
    page = (
        "# 6. Orchestrating Smarter Evaluation Procedures\n"
        "\n"
        "123\n"
        "\n"
        "Pink is for tax bills; why Lakisha needs a longer resume than Emily\n"
        "\n"
        "#### 7. Attracting the Right People\n"
        "\n"
        "146\n"
    )
    folio, _body = _strip(page)
    assert folio is None


def test_index_page_captures_nothing_rather_than_an_entry_number():
    """An index page is the same shape: wrapped entries leave bare numbers."""
    page = (
        "# Index\n"
        "\n"
        "Leadership\n"
        "books about,\n"
        "120\n"
        "\n"
        "Learning, books about,\n"
        "119\n"
    )
    folio, _body = _strip(page, header=frozenset())
    assert folio is None


# --- the property that makes the rule safe ---------------------------------

def test_ordinary_page_with_one_standalone_folio_is_unchanged():
    """The common case must be untouched: exactly one folio-shaped line."""
    page = (
        "42\n"
        "\n"
        "The manager's output is the output of the organisation under her.\n"
    )
    folio, body = _strip(page, header=frozenset())
    assert folio == "42"
    assert "manager's output" in body


def test_folio_in_foot_band_still_captured():
    """The Alliance runs its folio at the foot; that path must still work."""
    page = (
        "Employment in the Networked Age\n"
        "\n"
        "A tour of duty is a mutual pact.\n"
        "\n"
        "9\n"
    )
    folio, _body = _strip(page, header=frozenset(), footer=frozenset())
    assert folio == "9"


def test_body_page_quoting_a_single_number_is_unchanged():
    """One standalone number plus a real folio is two -- but this is the
    boundary the rule accepts as the price of correctness.

    A page whose body quotes a bare number loses its capture and falls back to
    interpolation. That is a coverage cost, never a correctness one, and it is
    the direction the runbook prefers to err.
    """
    page = (
        "17\n"
        "\n"
        "The result was unambiguous:\n"
        "\n"
        "94\n"
        "\n"
        "percent of respondents agreed.\n"
    )
    folio, _body = _strip(page, header=frozenset(), footer=frozenset())
    assert folio is None


def test_roman_folio_alone_still_captured():
    page = "xvii\n\nPreface to the second edition\n"
    folio, _body = _strip(page, header=frozenset())
    assert folio == "xvii"
