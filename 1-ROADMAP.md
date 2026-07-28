---
type: roadmap
scope: bookconvert
status: active
last_updated: 2026-04-27
---

# BookConvert — Roadmap

> Rolling punch list (Now / Next / Blocked / Someday). Update as work moves; drop items the moment they're done.
> Loaded into Claude sessions automatically via `CLAUDE.md`.
>
> Renamed from `docs/TASKS.md` on 2026-04-27 as part of the spine adoption (`8-DECISIONS/2026-04-27-spine-adoption.md`). Same role, spine-aligned filename and frontmatter.
>
> BookConvert is a small tool and does not carry a `0-STRATEGY.md`. For strategic context on why it exists, see the Management Craft STRATEGY.md under the MC Research Loop Acquire step. Publicly trackable bugs and features live in GitHub Issues at https://github.com/AndySparks/book-convert/issues.

## Now

_none currently_

## Next

_none currently_

## Blocked

_none currently_

## Someday

_none currently_

---

## Notes

**2026-07-28:** Closed issue #27 on branch `feat/epub-heading-fallback`. EPUBs that carry no semantic `h1`–`h6` (chapter openers styled `<p class="chaphead">` — hit on Landsberg, *Mastering Coaching*) were converting to one flat document with nothing in the sidecar to say so. New `epub_structure.py` reads the epub's spine, detects the condition, and derives headings from the book's own navigation (`toc.ncx` for EPUB 2, the nav document for EPUB 3), mapping nav nesting to heading depth and promoting the anchor's element in place when its text already *is* the nav label. A narrow chapter-ish CSS-class heuristic is the fallback to the fallback; it never overrides the nav. Pandoc gets a rewritten copy from a temp dir — the source epub is never touched. The sidecar now always declares `heading_source` (`semantic` | `nav` | `class-heuristic` | `none`) and `headings_emitted`, with warnings on the non-semantic and zero-heading cases; both fields stay `null` on the PDF backends, which don't measure them. New `tests/test_epub_headings.py` (36 tests) plus a configurable synthetic-EPUB builder in `tests/fixtures.py`. Full suite: 266 passing / 8 skipped on `.venv` (Py3.9), 272 passing / 2 skipped on `.venv-marker` (Py3.12).

**2026-07-03:** Shipped a default-on, verbatim-safe post-conversion cleanup pass (`cleanup.py`) on branch `feat/cleanup-pass`, prompted by an extensive manual cleanup of two Virginia Tufte books. De-joins dropped-space function-word joins (precision-first, with British-spelling / coinage / proper-noun / trailing-"a" guards — validated at ~200 joins per book with zero false splits), fixes stray-consonant citation ghosts, and unwraps picture-text TOC tables while dropping OCR garble. Runs by default (`--no-clean` to skip); records `cleaned`/`cleanup` stats on the report sidecar. Also fixed the `pymupdf4llm` image-path bug (refs were output-dir-prefixed/absolute, breaking relative to the md; now rewritten relative, matching the pymupdf backend). Added `pyspellchecker` to `requirements.txt` (pure-Python; cleanup degrades gracefully if absent). New tests: `tests/test_cleanup.py` + an image-ref regression test. Full suite: 87 passing on `.venv` (Py3.9, de-join tests skip without pyspellchecker), 111 passing on `.venv-marker` (Py3.12). See `8-DECISIONS/2026-07-03-post-conversion-cleanup.md`.

**2026-04-15:** Shipped BookConvert v2 improvements per `docs/bookconvert-improvements-plan-2026-04-15.md` on branch `feat/v2-improvements` (19 commits). New backends `pymupdf4llm` and `docling` wired up alongside the existing pymupdf/marker/ocr/pandoc set, each gated by a Python 3.10+ check that points at `.venv-marker`. New `--extract-images` flag renders figures, diagrams, and raster images as PNGs alongside the markdown via clipped `page.get_pixmap`; real-world proof: *Dont Make Me Think, Revisited* went from zero to 200 extracted figures. Every backend now writes a `.report.json` sidecar (method, page counts, OCR pages, extracted assets, quality score, warnings). Auto-OCR fallback now prefers marker over tesseract when marker is installed (closes the old "Next" item for issue #18). OCR-specific quality warnings surface `BARBAIA`-style consonant runs and `Ine.` artifacts without hard-failing. Requirements split into per-backend extras files (`requirements-marker.txt`, `requirements-pymupdf4llm.txt`, `requirements-docling.txt`, `requirements-ocr.txt`) so the default install stays slim. Full test suite: 79 passing on `.venv` (Python 3.9), 83 passing on `.venv-marker` (Python 3.12).

---

## How to update this file

- **Add** items as work gets deferred or surfaced during a session.
- **Remove** items the moment they're done. No archive. Git log is the history.
- **Move** items between buckets as priority shifts.
- `/start` surfaces items from "Now" and "Blocked" when opening the repo.
- `/wrap` prompts to update TASKS.md at session end.

## What does NOT go here

- **Publicly trackable bugs and features**: GitHub Issues, with a link here if blocking active work in this repo.
- **MC-wide tasks that happen to touch BookConvert**: Management Craft's `docs/TASKS.md`. BookConvert is infrastructure for MC's Research Loop Acquire step; strategic questions about the corpus live upstream.
- **Cross-project personal admin**: Notion Tasks DB.
