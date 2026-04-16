# BookConvert Tasks

> Rolling punch list. Update as work moves; drop items the moment they're done.
> Loaded into Claude sessions automatically via `CLAUDE.md`.
>
> BookConvert is a small tool and does not carry a `docs/STRATEGY.md`. For strategic context on why it exists, see the Management Craft STRATEGY.md under the MC Research Loop Acquire step. Publicly trackable bugs and features live in GitHub Issues at https://github.com/AndySparks/book-convert/issues.

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
