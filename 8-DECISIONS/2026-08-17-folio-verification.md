---
type: decision
date: 2026-08-17
status: accepted
tags: [locators, quality, ocr, verification]
---

# A converted scan can prove its own page numbers

## Decision

Ship `verify_folios.py`: read the printed folio off every page image of a scanned
PDF and report whether the book's pagination is coherent. Detect a shift as a
**transition between two established offsets**, never as "the offset that is less
common".

The tool knows nothing about any corpus. It takes a PDF and reports what its pages
say. Comparing that against a converted file's own markers belongs downstream, in
whatever holds those files.

## Why

`convert.py` captures folios where it can and **interpolates** the rest from a
consensus offset (`_OFFSET_CONSENSUS_MIN_AGREEMENT`, the consensus rule). That is
correct behaviour: a folio hidden under a fold, inside a figure, or on a chapter
opener should not leave a hole in the locator sequence.

But it leaves the output part measured and part computed, with nothing afterwards
able to tell the two apart. Coverage figures make this concrete — one book in the
Management Craft corpus carries `page_printed_coverage: 0.095`. Nine in ten of its
page numbers were never read off a page.

Interpolation is sound exactly as far as the offset is. The failure it cannot
survive is a **pagination shift**: an unnumbered plate section, a bound-in map, an
inserted errata leaf. Every folio after it moves, one constant offset is applied
over the top, and the result is smooth, self-consistent, and wrong from that point
onward. A reader sent to page 214 finds page 206.

The decisive property is that **interpolation does not merely fail to catch this —
it smooths it.** The more thoroughly a file is interpolated, the more perfectly
coherent a shifted book looks. So the check cannot be internal to the conversion.
It has to go back to the images.

## Why a transition, not a minority

The first implementation asked which offset was most common and called everything
else an anomaly. It inverts: put a plate section a third of the way into a book and
the shifted region is the *majority*, so the tool indicts the correct pages and
blesses the wrong ones.

A pagination shift is not a minority. It is a change that persists. Two established
runs — each long enough that OCR noise cannot fake one — meeting at different
offsets is the signature, and it has no orientation. It does not care which side is
bigger.

This was caught by a test, not by review. `test_the_shift_is_caught_even_when_it_covers_MOST_of_the_book`
is that case and stays as the regression.

## Noise versus signal

Real corpus behaviour, from four books read end to end:

- **Noise** is scattered. Pages disagree individually, each implying its own
  offset (-84, -192, -230 in one book). tesseract has picked a note number, a
  figure callout, or a table value out of the margin band.
- **A digit-confusion class** is still noise. One book read `81` as `31`, `85` as
  `35`, `181` as `131` — same wrong offset three times, on pages far apart. An 8
  misread as a 3 is not a shift.
- **A shift** moves adjacent pages together and keeps them there.

`MIN_ANOMALY_RUN = 3` is the floor. Two consecutive misreads happen — facing pages
share a scan artifact — and three consecutive pages agreeing on a new offset do not.

## Refusing to answer

Below `MIN_READ_FRACTION` the tool reports **inconclusive** and exits 2. A check
that reads almost nothing and then reports no problem is worse than no check,
because it is indistinguishable from a pass. "No shift found" and "no data" are
different answers and get different exit codes.

## Two ways to be confidently wrong, both found by review

Independent review (codex) found that the first implementation could return either
verdict falsely, which for a tool whose entire job is a verdict is the whole ballgame.
Both are now regression tests.

**False clean.** If OCR lifts a non-folio out of the band — `CHAPTER 4` on every
page — every page reports the same number, so every page implies a *different*
offset, so no segment forms, so no transition is found. The tool reported no shift
and exited 0 without having read a single real folio. Read fraction cannot see
this: the pages were read, they just said nothing. **A result is now conclusive
only when some offset is ESTABLISHED** — supported by adjacent pages agreeing —
and otherwise reports "no stable offset" and exits 2.

**False anomaly.** Segments ignored index gaps entirely, so three pages agreeing at
one offset on pages 10, 20 and 30 with everything between unread became an
established run, and a transition was manufactured against a perfectly good book.
That is the exact far-apart pattern this document already classified as noise, so
the code contradicted its own spec. Segments now break across a gap larger than
`MAX_SEGMENT_GAP`. Splitting a genuine segment costs nothing: two segments at the
same offset yield no transition.

The pair is the lesson. A verdict tool needs both failure directions tested, not
just the one it was written to catch.

## Consequences

- New optional dependency on `tesseract` for this tool only. `pytesseract` is used
  when present (`requirements-ocr.txt`); otherwise the binary is called directly.
  Conversion is unaffected.
- The analysis half is pure and directly testable, so the OCR half does not have to
  run in tests.
- Downstream consumers get a machine-readable verdict via `--json`.
