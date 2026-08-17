"""Tests for verify_folios.

The analysis half is pure, so it is tested directly against constructed folio maps. That
matters more than an end-to-end OCR test here: the thing worth getting right is the
distinction between OCR noise and a real pagination shift, and that distinction is a
property of `analyse`, not of tesseract.

Both halves are covered, per the rule that a filter is only verified when the bad case is
gone AND the legitimate population still passes: a book with scattered misreads must come
back CLEAN, and a book with an inserted plate section must come back ANOMALOUS.
"""
import pytest

from verify_folios import MIN_ANOMALY_RUN, analyse, find_transitions, folio_from_text


# ── reading a folio out of an OCR'd band ─────────────────────────────────────────────

def test_folio_alone_on_its_line():
    assert folio_from_text("214\n") == 214


def test_folio_beside_a_running_head():
    assert folio_from_text("214  The Knowing-Doing Gap\n") == 214
    assert folio_from_text("The Knowing-Doing Gap  214\n") == 214


def test_number_buried_mid_line_is_not_a_folio():
    # A citation or a figure callout. Taking this would invent a page number.
    assert folio_from_text("as Argyris showed in 1977 the gap persists\n") is None


def test_empty_band():
    assert folio_from_text("") is None
    assert folio_from_text("\n\n  \n") is None


def test_five_digit_number_is_not_a_folio():
    assert folio_from_text("100000\n") is None


# ── the clean case: a well-numbered book with OCR noise ──────────────────────────────

def _clean_book(n=100, offset=-17):
    return {i: i + offset for i in range(20, 20 + n)}


def test_a_clean_book_reports_no_anomaly():
    r = analyse(_clean_book(), total_pages=140)
    assert r["dominant_offset"] == -17
    assert r["anomalies"] == []
    assert r["conclusive"] is True


def test_scattered_misreads_are_noise_not_an_anomaly():
    """The real shape from pfeffer-sutton: three pages misread, each differently."""
    folios = _clean_book()
    folios[40] = 2      # tesseract grabbed a note number
    folios[86] = 2
    folios[110] = 7
    r = analyse(folios, total_pages=140)
    assert len(r["disagreeing_pages"]) == 3
    assert r["anomalies"] == [], "isolated misreads must not be called a pagination shift"


def test_two_adjacent_misreads_are_still_noise():
    """Facing pages share a scan artifact. The floor is MIN_ANOMALY_RUN."""
    folios = _clean_book()
    folios[50] = 999
    folios[51] = 999
    r = analyse(folios, total_pages=140)
    assert r["anomalies"] == []


def test_a_digit_confusion_class_does_not_trigger_an_anomaly():
    """jay-the-defining-decade: an 8 read as a 3 on three NON-adjacent pages."""
    folios = _clean_book()
    for p, wrong in ((60, 60 - 17 - 50), (64, 64 - 17 - 50), (160 - 60, 100 - 17 - 50)):
        folios[p] = wrong
    r = analyse(folios, total_pages=140)
    assert r["anomalies"] == [], "same wrong offset, but not adjacent — still noise"


# ── the case the tool exists for ─────────────────────────────────────────────────────

def test_an_inserted_plate_section_is_caught():
    """Eight unnumbered plate pages bound in at page 60. Every folio after shifts by 8,
    and interpolation from one constant offset would render all of them smoothly wrong."""
    folios = {}
    for i in range(20, 60):
        folios[i] = i - 17
    for i in range(60, 120):
        folios[i] = i - 17 - 8
    r = analyse(folios, total_pages=140)
    assert len(r["anomalies"]) == 1
    a = r["anomalies"][0]
    assert a["last_page_before"] == 59
    assert a["first_page_after"] == 60
    assert (a["from_offset"], a["to_offset"]) == (-17, -25)
    assert a["shift"] == -8


def test_the_shift_is_caught_even_when_it_covers_MOST_of_the_book():
    """The regression that killed the first design. Detecting the anomaly as "the offset
    that is not most common" inverts here: the shifted region is larger, so the GOOD pages
    became the anomaly. A transition has no such orientation."""
    folios = {**{i: i - 17 for i in range(20, 40)}, **{i: i - 25 for i in range(40, 130)}}
    r = analyse(folios, total_pages=140)
    assert len(r["anomalies"]) == 1
    assert (r["anomalies"][0]["from_offset"], r["anomalies"][0]["to_offset"]) == (-17, -25)


def test_a_gap_of_unread_pages_does_not_split_a_segment():
    """Pages tesseract could not read are absent, not a boundary."""
    folios = {i: i - 17 for i in range(20, 60) if i not in (33, 34, 47)}
    r = analyse(folios, total_pages=80)
    assert r["anomalies"] == []


def test_alternating_misreads_are_not_a_transition():
    offsets = {10: -17, 11: -25, 12: -17, 13: -25, 14: -17}
    assert find_transitions(offsets) == []


def test_exactly_the_minimum_run_counts():
    folios = _clean_book()
    for i in range(70, 70 + MIN_ANOMALY_RUN):
        folios[i] = i - 17 - 9
    r = analyse(folios, total_pages=140)
    # In and out again: two transitions, -17 -> -26 and -26 -> -17.
    assert len(r["anomalies"]) == 2
    assert r["anomalies"][0]["shift"] == -9


def test_one_short_of_the_minimum_does_not():
    folios = _clean_book()
    for i in range(70, 70 + MIN_ANOMALY_RUN - 1):
        folios[i] = i - 17 - 9
    r = analyse(folios, total_pages=140)
    assert r["anomalies"] == []


# ── refusing to answer ───────────────────────────────────────────────────────────────

def test_too_few_folios_is_inconclusive_not_clean():
    """A check that reads almost nothing and reports no anomaly looks exactly like a
    pass. It must not be one."""
    r = analyse({20: 3, 21: 4}, total_pages=400)
    assert r["conclusive"] is False
    assert r["anomalies"] == []


def test_no_folios_at_all():
    r = analyse({}, total_pages=100)
    assert r["conclusive"] is False
    assert r["dominant_offset"] is None


def test_zero_pages_does_not_divide_by_zero():
    r = analyse({}, total_pages=0)
    assert r["read_fraction"] == 0.0


# ── the CLI contract ─────────────────────────────────────────────────────────────────

def test_exit_codes_are_distinguishable():
    """0 clean, 1 anomaly, 2 cannot say — a caller must be able to tell 'no problem'
    from 'no data'."""
    clean = analyse(_clean_book(), total_pages=140)
    shifted = analyse(
        {**{i: i - 17 for i in range(20, 60)}, **{i: i - 30 for i in range(60, 120)}},
        total_pages=140,
    )
    thin = analyse({20: 3}, total_pages=400)
    assert (clean["conclusive"], bool(clean["anomalies"])) == (True, False)
    assert (shifted["conclusive"], bool(shifted["anomalies"])) == (True, True)
    assert thin["conclusive"] is False
