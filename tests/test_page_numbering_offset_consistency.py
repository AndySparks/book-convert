"""`page_numbering: printed` is a licence to cite, and must be earned.

WHY THIS EXISTS

mc-wiki's `tools/cite.py` refuses to cite a source by page unless its
`page_numbering` reads "printed". So this one string decides whether page
numbers out of a conversion can reach a citation.

It used to be set from `captured > 0` alone — any folio anywhere earned the
licence, however incoherent the pagination.

Found 2026-09-01 by the annotated edition of *The Human Side of Enterprise*:
30 folios captured across 480 sheets (coverage 0.062), with the sidecar
stating that the best-supported offset was carried by 1 of 30 (3%, against an
85% consensus bar) — and `page_numbering` still reading "printed". The captured
values were sheet 56 -> "1", 72 -> "2", 85 -> "4", 99 -> "3", i.e. the
annotated edition's marginal annotation numbers read as folios.
"""
import pytest

from convert import (_decide_page_numbering, _page_offset_support,
                     _page_offset_outliers)


def test_no_folios_is_pdf_only():
    assert _decide_page_numbering(0, False, None) == "pdf_only"
    assert _decide_page_numbering(0, True, 1.0) == "pdf_only"


def test_a_consistent_offset_earns_printed():
    """The green case: the licence is still granted where it is deserved."""
    assert _decide_page_numbering(127, True, 1.0) == "printed"
    assert _decide_page_numbering(3, True, 1.0) == "printed"


def test_incoherent_folios_lose_the_licence():
    """The McGregor case, and the whole point of the change.

    30 folios captured across 480 sheets, the dominant offset carried by 1 of
    them. Those were the annotated edition's marginal annotation numbers.
    """
    assert _decide_page_numbering(30, False, 1 / 30) == "pdf_only"


def test_a_book_that_merely_RENUMBERS_keeps_the_licence():
    """The half the first draft of this fix got wrong.

    Refusing every inconsistent book would have demoted 22 real sources,
    including The Achievement Motive (67% support, 340 folios, 89.5% coverage)
    and Scaling People (99.2% coverage). Renumbering is ordinary; incoherence
    is not. Every support figure observed in the corpus outside McGregor:
    """
    for support in (0.54, 0.57, 0.67, 0.75, 0.77, 0.79, 0.84):
        assert _decide_page_numbering(200, False, support) == "printed", support


def test_the_threshold_sits_in_the_observed_gap():
    """3% and 54% are the two neighbours; the boundary must separate them."""
    assert _decide_page_numbering(30, False, 0.03) == "pdf_only"
    assert _decide_page_numbering(30, False, 0.54) == "printed"


def test_unjudgeable_support_leaves_the_verdict_alone():
    """Too few samples is a DIFFERENT defect (sparse capture), out of scope.

    Widening into it would demote four more sources on a question this change
    did not investigate.
    """
    assert _decide_page_numbering(1, False, None) == "printed"
    assert _decide_page_numbering(2, False, None) == "printed"


def test_support_is_computed_from_the_samples():
    # Six arabic folios: five at offset -5, one dissenting at -3.
    samples = {10: "5", 11: "6", 12: "7", 13: "8", 14: "9", 20: "17"}
    support = _page_offset_support(samples)
    assert support == pytest.approx(5 / 6)


def test_support_is_none_below_the_sample_floor():
    assert _page_offset_support({10: "5"}) is None
    assert _page_offset_support({}) is None


@pytest.mark.parametrize("captured,consistent,support,expected", [
    (0, False, None, "pdf_only"),
    (1, True, 1.0, "printed"),
    (30, False, 0.03, "pdf_only"),   # the-human-side-of-enterprise-annotated
    (13, False, 0.54, "printed"),    # on-the-edge
    (340, False, 0.67, "printed"),   # the-achievement-motive
    (127, True, 1.0, "printed"),     # fitzpatrick-the-mom-test
])
def test_truth_table(captured, consistent, support, expected):
    assert _decide_page_numbering(captured, consistent, support) == expected


# ---------------------------------------------------------------------------
# End-to-end: derive support from a real sample map, not an injected number.
#
# codex round 1 caught that every test above hands `_decide_page_numbering` a
# support value directly, so deleting the argument from BOTH production call
# sites would leave them all green. These drive the actual derivation path.
# ---------------------------------------------------------------------------

from convert import _derive_page_offset


def _mcgregor_like():
    """The annotated-edition shape: captured values that are not folios.

    Sheet 56 -> "1", 72 -> "2", 85 -> "4", 99 -> "3" and so on: marginal
    annotation numbers, each giving a different offset.
    """
    return {56: "1", 72: "2", 85: "4", 99: "3", 113: "5", 130: "6",
            148: "7", 161: "8", 177: "9", 190: "10"}


def _coherent_book(n=40, offset=-5):
    return {i: str(i + offset) for i in range(10, 10 + n)}


def _renumbering_book():
    """Coherent body plus a second sequence — the case that must SURVIVE."""
    d = {i: str(i - 5) for i in range(10, 40)}      # 30 samples at -5
    d.update({i: str(i - 60) for i in range(70, 82)})  # 12 at -60
    return d


def test_end_to_end_incoherent_captures_lose_the_licence():
    samples = _mcgregor_like()
    offset, consistent = _derive_page_offset(samples)
    support = _page_offset_support(samples)
    assert consistent is False
    assert support < 0.5, support
    assert _decide_page_numbering(len(samples), consistent, support) == "pdf_only"


def test_end_to_end_a_coherent_book_keeps_the_licence():
    samples = _coherent_book()
    offset, consistent = _derive_page_offset(samples)
    support = _page_offset_support(samples)
    assert consistent is True and support == 1.0
    assert _decide_page_numbering(len(samples), consistent, support) == "printed"


def test_end_to_end_a_renumbering_book_keeps_the_licence():
    """30 of 42 samples agree — refused as an offset, but far from incoherent."""
    samples = _renumbering_book()
    offset, consistent = _derive_page_offset(samples)
    support = _page_offset_support(samples)
    assert consistent is False
    assert support > 0.5, support
    assert _decide_page_numbering(len(samples), consistent, support) == "printed"


def test_support_is_measured_before_outliers_are_removed():
    """The ordering bug codex round 1 found (P2).

    The production paths delete every capture contradicting an adopted offset.
    Measuring support after that sweep reads ~1.0 for any book that got an
    offset, which is both useless and a false description of the field.
    """
    samples = dict(_coherent_book(n=17))
    samples[100] = "1"            # one contradicting capture
    before = _page_offset_support(samples)
    assert before == pytest.approx(17 / 18)

    offset, consistent = _derive_page_offset(samples)
    outliers = _page_offset_outliers(samples, offset if consistent else None)
    for i in outliers:
        del samples[i]
    after = _page_offset_support(samples)
    assert after == 1.0
    assert before != after, "the sweep must actually change the figure"


# ---------------------------------------------------------------------------
# The integration test. Everything above calls the decision function directly,
# so deleting the support argument from the production call sites leaves them
# green — codex round 1 pointed that out and it was still true after the first
# round of "end-to-end" tests. This one runs a real conversion and reads the
# verdict off the report, which is the only thing that can catch it.
# ---------------------------------------------------------------------------

from tests.fixtures import build_page_printed_pdf


def test_conversion_of_an_incoherent_book_reports_pdf_only(tmp_path):
    """A book whose captured folios do not agree must not be called citable.

    Every page prints a number, but the numbers are mutual nonsense — the
    shape the annotated Human Side of Enterprise produced when marginal
    annotation numbers were read as folios.
    """
    import convert
    nonsense = {i: str((i * 7) % 11 + 1) for i in range(1, 21)}
    pdf = build_page_printed_pdf(
        tmp_path, pages=20, offset=-4,
        misread_page_printed_on=nonsense, name="incoherent.pdf")

    outdir = tmp_path / "out"
    outdir.mkdir()          # this branch is independent of the sibling PR that
                            # makes convert_with_pymupdf create its own outdir
    report = convert.convert_with_pymupdf(pdf, outdir)

    assert report.page_printed_count > 0, "fixture must capture folios"
    assert report.page_printed_offset_consistent is False
    assert report.page_printed_offset_support is not None
    assert report.page_printed_offset_support < 0.5, \
        report.page_printed_offset_support
    assert report.page_numbering == "pdf_only", (
        "captured folios that do not cohere must not earn the citation licence"
    )


def test_conversion_of_a_coherent_book_still_reports_printed(tmp_path):
    """The other half: an ordinary book keeps its page-citability."""
    import convert
    pdf = build_page_printed_pdf(tmp_path, pages=20, offset=-4,
                                 name="coherent.pdf")
    outdir = tmp_path / "out2"
    outdir.mkdir()
    report = convert.convert_with_pymupdf(pdf, outdir)
    assert report.page_printed_offset_consistent is True
    assert report.page_numbering == "printed"
    assert report.page_printed_offset_support == 1.0
