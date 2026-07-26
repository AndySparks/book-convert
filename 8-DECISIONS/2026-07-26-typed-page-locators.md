---
type: decision
date: 2026-07-26
status: accepted
tags: [conversion, citation, locators]
---

# Typed page locators: PDF page index and printed page number are different things

## Context

BookConvert emitted `<!-- Page N -->` from three of six backends, where N was
the PDF page index. Downstream, that was being read as a page number. It is
not one. `_strip_running_headers()` was separately deleting the printed page
number as noise, so the one citation-valid address was discarded on every
conversion.

## Decision

Emit both addresses, and declare which exists:

    <!-- page_pdf=59 page_printed=47 -->

- `page_pdf` — PDF page index. Always accurate, sparse. For navigation.
- `page_printed` — the number printed on the page. For citation. `none` when
  absent.

The sidecar declares `page_numbering` (`printed` | `pdf_only` | `none`) and
`page_printed_coverage`. Every locator-emitting backend writes a sidecar,
including backends that cannot produce printed page numbers at all — they say
so explicitly rather than emitting nothing silently. `pandoc` (EPUB) is the
clearest case: an EPUB is reflowable and has no pages to address, so
`convert_with_pandoc` still writes a `.report.json` sidecar, declaring
`page_numbering: "none"`. Silence would be indistinguishable from a
conversion that never ran; a sidecar that says "no locators exist" is a
positive, checkable claim the ingestion gate can act on.

Printed page numbers are interpolated across gaps only under three guards,
together:

1. **At least 3 captured arabic samples, all agreeing** on a constant
   page_pdf→page_printed offset (`_derive_page_offset`). Roman page numbers
   never participate — they belong to a separate numbering sequence. Fewer
   than 3 samples, or any disagreement (e.g. a part-opener restarting at 1),
   and `page_printed_offset_consistent` is `False`: no interpolation anywhere
   in the book.
2. **Clamped to the closed interval between the first and last captured
   arabic sample** (`_arabic_page_pdf_indices` / `page_pdf_span`).
   Interpolation never extends past the last real observation — end matter or
   a second numbering sequence past the final sample contributes no samples,
   so it cannot disagree, and extrapolating there would invent confident
   wrong page numbers a reader cannot detect.
3. **Never below 1.** Even inside the clamped span, a derived candidate
   printed page number less than 1 is discarded rather than emitted — pages
   that precede printed page 1 stay `page_printed=none`.

Andy ratified interpolation-with-guards over observed-page-numbers-only on
2026-07-26. The tradeoff is deliberate: captured printed page numbers are
sparse (running headers/footers survive cleanup on only a fraction of pages —
Grove's 319-page scan yielded ~20 readable printed page numbers), so
observed-only would leave roughly 94% of a citable book uncitable. The three
guards above are what make deriving the other 94% safe rather than a guess.

## Consequences

- **Breaking output-format change.** Consumers matching `<!-- Page (\d+) -->`
  break. The known consumer is mc-wiki's `tools/wiki-maintain.py`. The 217
  already-converted vault files retain the old format until reconverted, so
  consumers must parse both formats during the transition.
- **Only `pymupdf` can produce a citable page number.** The full per-backend
  capability map (`BACKEND_PAGE_NUMBERING`, `convert.py`) is:

  | Backend | `page_numbering` | Citable by page? |
  |---|---|---|
  | `pymupdf` | decided at runtime — `printed` if any printed page number was captured, else `pdf_only` | Yes, when `printed` |
  | `pymupdf4llm` | `pdf_only` (fixed) | No |
  | `ocr` | `pdf_only` (fixed) | No |
  | `marker` | `none` (fixed) | No |
  | `pandoc` | `none` (fixed) | No |
  | `docling` | `none` (fixed) | No |

  `pymupdf` is deliberately absent from `BACKEND_PAGE_NUMBERING` — it is the
  one backend that decides its own `page_numbering` at the end of a
  conversion, so do not treat it as having a fixed value.

  All three `none` backends — `marker`, `pandoc`, `docling` — declare
  `page_numbering: "none"` always, with no interpolation attempted. Sources
  ingested through them cannot be cited by page: for `pandoc` because EPUB is
  reflowable and no page number exists to cite; for `marker` and `docling`
  because neither pipeline currently exposes a page address we can trust.

## Alternatives rejected

- **Keep `<!-- Page N -->` and document that it means PDF page index.**
  Rejected: the failure is silent and a reader cannot detect it. The whole
  point is to make a PDF page index unusable as a page number.
- **Infer printed page numbers with a model.** Rejected: inventing a page
  number that is not printed on the page is exactly the failure this
  prevents.
- **Observed printed page numbers only, no interpolation.** Rejected: given
  how sparse captured printed page numbers are in practice, this would leave
  the large majority of a book uncitable by page even when the offset is
  provably constant. The three guards (≥3 agreeing samples, clamped span,
  floor of 1) make derivation safe enough to prefer over leaving nearly the
  whole book unaddressed.

Full investigation: management-craft `docs/2B-PROJECTS/page-locator-pipeline/v1/RESEARCH.md`.
