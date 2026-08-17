"""Tests for verify_folios.

The analysis half is pure, so it is tested directly against constructed folio maps. That
matters more than an end-to-end OCR test here: the thing worth getting right is the
distinction between OCR noise and a real pagination shift, and that distinction is a
property of `analyse`, not of tesseract.

Both halves are covered, per the rule that a filter is only verified when the bad case is
gone AND the legitimate population still passes: a book with scattered misreads must come
back CLEAN, and a book with an inserted plate section must come back ANOMALOUS.
"""
import json
import sys

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


# ── codex round 1, 2026-08-17: two verdicts that were confidently wrong ──────────────

def test_a_misread_constant_is_not_a_clean_book():
    """OCR lifts 'CHAPTER 4' out of the band on every page. Same number everywhere, so a
    DIFFERENT offset on every page, so no segment, so no transition — and the tool used to
    call that clean and exit 0 without having read one real folio. Read fraction cannot
    see this; only the absence of an established offset can."""
    r = analyse({i: 4 for i in range(20, 120)}, total_pages=140)
    assert r["conclusive"] is False, "no stable offset must be inconclusive, never clean"
    assert r["pages_in_established_runs"] == 0


def test_far_apart_readings_do_not_form_a_run():
    """Three pages agreeing at one offset with everything between them unread are three
    coincidences, not a run. Chaining them manufactured a transition against a good book —
    and contradicted this tool's own decision doc, which classes that pattern as noise."""
    folios = {10: 3, 20: 13, 30: 23, **{i: i - 17 for i in range(40, 90)}}
    r = analyse(folios, total_pages=140)
    assert r["anomalies"] == []


def test_a_small_gap_still_holds_a_segment_together():
    """The other half: tesseract missing a few pages must not split a real book."""
    folios = {i: i - 17 for i in range(20, 90) if i not in (40, 41, 42)}
    r = analyse(folios, total_pages=140)
    assert r["anomalies"] == []
    assert r["conclusive"] is True


def test_a_real_shift_survives_the_gap_rule():
    """The gap rule must not have disarmed the detector it protects."""
    folios = {**{i: i - 17 for i in range(20, 60)}, **{i: i - 25 for i in range(60, 110)}}
    r = analyse(folios, total_pages=140)
    assert len(r["anomalies"]) == 1
    assert r["anomalies"][0]["shift"] == -8


# ── widening the band when the first pass cannot conclude ────────────────────────────

def test_wider_bands_are_ordered_and_above_the_default():
    from verify_folios import WIDER_BANDS
    assert list(WIDER_BANDS) == sorted(WIDER_BANDS)
    assert all(b > 0.11 for b in WIDER_BANDS), "a retry narrower than the default cannot help"


def test_the_band_is_reported_so_a_verdict_can_be_reproduced():
    """Two runs of the same book can now read different numbers of folios depending on the
    band that succeeded. A verdict that does not say which band produced it cannot be
    checked by anyone."""
    from verify_folios import render
    r = analyse(_clean_book(), total_pages=140)
    r["band"] = 0.17
    assert "margin band 0.17" in render(r)


def test_widening_cannot_change_a_conclusive_verdict():
    """The loop breaks on the first conclusive result, so a book that concludes at the
    default band is never re-read at a wider one. Asserted on the predicate the loop uses,
    because the loop itself needs a PDF."""
    conclusive = analyse(_clean_book(), total_pages=140)
    assert conclusive["conclusive"] is True
    # A real shift must still be visible at the first band, not masked by a later retry.
    shifted = analyse(
        {**{i: i - 17 for i in range(20, 60)}, **{i: i - 25 for i in range(60, 110)}},
        total_pages=140,
    )
    assert shifted["conclusive"] is True and len(shifted["anomalies"]) == 1


def _fake_fitz(pages):
    """A stand-in for PyMuPDF. main() opens the document only to count its pages."""
    import types
    doc = types.SimpleNamespace(page_count=pages, close=lambda: None)
    return types.SimpleNamespace(open=lambda *a, **k: doc)


def test_main_actually_retries_at_a_wider_band(tmp_path, monkeypatch, capsys):
    """Drive the real loop in main().

    The first attempt at this feature was a silent no-op: the patch that added the loop
    failed to apply, so `--no-widen` existed and did nothing while the constants and the
    render line were both present and tested. Every test passed. Nothing exercised main().

    A test that cannot observe the behaviour it names is not a test of it — so this one
    stubs read_folios per band and asserts the narrow band's answer is NOT what comes out.
    """
    import verify_folios as vf

    calls = []

    def fake_read_folios(pdf, dpi=300, band=0.11, pages=None, progress=None):
        calls.append(band)
        if band < 0.15:
            return {i: 4 for i in range(0, 30)}          # no stable offset -> inconclusive
        return {i: i - 17 for i in range(0, 100)}         # legible at the wider band

    # fitz is imported INSIDE the functions, so the module object is what gets stubbed.
    monkeypatch.setattr(vf, "read_folios", fake_read_folios)
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(140))
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "r.json"
    monkeypatch.setattr(sys, "argv", ["verify_folios.py", str(pdf), "--quiet", "--json", str(out)])

    rc = vf.main()
    assert len(calls) > 1, "main() never retried — the widening loop is a no-op"
    assert calls[0] < calls[1], "the retry must be WIDER than the first attempt"
    assert rc == 0
    result = json.loads(out.read_text())
    assert result["conclusive"] is True
    assert result["band"] == calls[-1]


def test_no_widen_really_disables_the_retry(tmp_path, monkeypatch):
    """A flag that does nothing is worse than no flag: it sends the operator to change
    something that cannot help, and the tool keeps failing for the reason they just fixed."""
    import verify_folios as vf

    calls = []

    def fake_read_folios(pdf, dpi=300, band=0.11, pages=None, progress=None):
        calls.append(band)
        return {i: 4 for i in range(0, 30)}

    monkeypatch.setattr(vf, "read_folios", fake_read_folios)
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(140))
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(sys, "argv", ["verify_folios.py", str(pdf), "--quiet", "--no-widen"])

    assert vf.main() == 2
    assert calls == [0.11], "--no-widen must leave exactly one attempt"
