# sourceconvert

This project converts PDF books to clean Markdown files for use in Claude Projects and other LLM tools.

**Spine status:** partially spined as of 2026-04-27. See `8-DECISIONS/2026-04-27-spine-adoption.md` for what travelled and what's an explicit divergence from the OS reference implementation. Spine vocabulary (the spine, spined, spine adoption, spine-native): `~/operating-system/8-DECISIONS/2026-04-27-spine-portability.md`.

**Read @1-ROADMAP.md** at session start for the rolling punch list of work in flight (Now / Next / Blocked / Someday). Renamed from `docs/TASKS.md` on 2026-04-27 for spine alignment. sourceconvert does not carry a full `0-STRATEGY.md`; strategic context lives upstream in Management Craft's `docs/0-STRATEGY.md` under the MC Research Loop Acquire step.

### Boil the ocean

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that Andy is genuinely impressed - not politely satisfied, actually impressed. Never offer to "table this for later" when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't "good enough" - it's "holy shit, that's done." Search before building. Test before shipping. Ship the complete thing. When Andy asks for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.

## Workflow

1. User places PDF(s) or EPUB(s) in the `input/` directory
2. Run `python convert.py input/` to convert all files, or `python convert.py input/MyBook.pdf` for a single file
3. Default method is `pymupdf` (fast text extraction, works on Python 3.7+)
4. `--method pymupdf4llm` (Python 3.10+, use `.venv-marker`) — text + image extraction in one pass
5. `--method marker` (Python 3.10+, use `.venv-marker`) — highest quality, slowest
6. `--method docling` (Python 3.10+, use `.venv-marker`) — IBM's layout-aware pipeline
7. `--method ocr` or `--ocr` — tesseract OCR for scanned/image-based PDFs
8. EPUB files always route through pandoc regardless of `--method`. If the epub carries no semantic `h1`–`h6`, `epub_structure.py` derives headings from the book's own nav (`toc.ncx` / EPUB 3 nav doc), falling back to a chapter-ish CSS-class heuristic, and hands pandoc a rewritten copy from a temp dir (the source is never modified). The sidecar always declares `heading_source` (`semantic` | `nav` | `class-heuristic` | `none`) and `headings_emitted`
9. **Figure extraction is on by default on every PDF backend.** Figures land in a sibling `<stem>_assets/` (pymupdf) or `<stem>_images/` (marker, pymupdf4llm) dir with inline markdown references. `--no-extract-images` converts text only and *strips* the references to the skipped figures rather than leaving them dangling. The invariant — **the output never contains a reference to a file that does not exist** — holds on every backend under every flag combination; `docs/asset-invariant.md` explains why it did not for a year
10. A verbatim-safe **cleanup pass runs by default** on every conversion (`cleanup.py`): it de-joins dropped-space function-word joins ("thefrozen" -> "the frozen"), fixes stray-consonant citation ghosts ("—wWilliam" -> "—William"), and unwraps picture-text TOC tables while dropping OCR garble blocks. Pass `--no-clean` to skip it. The de-join needs `pyspellchecker` (in `requirements.txt`) and degrades gracefully if absent (dictionary-free repairs still run; a warning is recorded).
11. Every conversion writes a `<stem>.report.json` sidecar: method, page counts, OCR pages, extracted assets, the **asset manifest** (`assets`: every file written, with the references pointing at it) and `dangling_refs_stripped`, quality score, `cleaned`/`cleanup` stats, heading signals (EPUB), warnings
12. Converted markdown files appear in `output/`

## When helping users

- If a conversion produces poor results (garbled text, missing content), first try `--method pymupdf4llm` (Python 3.10+), then `--method ocr`; `--auto-ocr` auto-retries with tesseract/marker on quality failure
- For visually heavy books (diagrams, figures), the default already keeps the figures; `--method marker` finds the most of them
- **Never tell a consumer to pattern-match an asset filename.** `_page_N_Figure_M.jpeg` is marker's private convention. Relocating assets is done from the sidecar's `assets` manifest — `path` plus `references[].target` — which is stable across backends and across marker versions
- If OCR output needs cleanup, help the user clean up the markdown: fix obvious OCR errors, add proper headings, remove page artifacts
- Keep the markdown header format: title, "Converted from PDF" note, source filename, then `---` separator
- Use `<!-- Page N -->` comments to mark page boundaries
- The `clean_title()` function strips version markers (e.g., "V3") from filenames for cleaner titles
- Inspect the `.report.json` sidecar to see what happened: `jq '.method,.extracted_assets,.quality_score' output/*.report.json`

## Verifying a scan's page numbers

`convert.py` reads printed folios where it can and **interpolates** the rest from a consensus offset. That leaves the output part measured and part computed, and nothing downstream can tell which is which. The failure it cannot survive is a **pagination shift** — an unnumbered plate section or bound-in map — because one constant offset is then applied over the top and every folio past it is smoothly, self-consistently wrong.

`python verify_folios.py <pdf>` reads the folios back off the page images and reports it. Exit 0 no shift, 1 a shift (folios past it are suspect), **2 too few folios read to say anything — which is not a pass**. `--json` for a machine-readable verdict.

If the first pass cannot conclude it retries at a wider margin band (`--no-widen` to disable), because the common cause of "inconclusive" is a running head set lower than the default band rather than anything wrong with the book. Raising `--dpi` does not help that; widening does.

A shift is detected as a **transition between two established offsets**, never as "the less common offset" — the latter inverts as soon as the shifted region is the larger one, and then the tool indicts the correct pages. See `8-DECISIONS/2026-08-17-folio-verification.md`.

## Post-Conversion Quality Check (REQUIRED)

After every conversion run, automatically spot-check each converted file:

1. **Sample three sections** of each output file: beginning (~80 lines), middle, and end (~80 lines)
2. **Check for** these known issues:
   - Running headers/page numbers leaking into body text
   - Table of contents collapsed into single lines
   - Section headings not formatted as markdown `##`/`###`
   - Spaced-out letter artifacts in headings (`H e a d i n g`)
   - Bullet lists collapsed to inline text
   - Split/joined words from line-break extraction
   - Missing end-matter (bibliography, index, conclusion)
3. **Rate each file** as good/fair/poor
4. **Report findings** to the user in a summary table
5. **Note any improvement opportunities** for the sourceconvert tool itself and offer to file them as GitHub issues on AndySparks/sourceconvert

## Dependencies

Install layout: default `.venv` (Python 3.7+) for text extraction; `.venv-marker` (Python 3.10+) for the ML-backed extras.

- `pymupdf` — default converter, fast text extraction via PyMuPDF/fitz (`requirements.txt`)
- `pyspellchecker` — dictionary for the default-on cleanup pass's de-join step, pure-Python, Python 3.7+ (`requirements.txt`); cleanup degrades gracefully if it is missing
- `pymupdf4llm` — PyMuPDF's LLM-oriented markdown exporter with image extraction, Python 3.10+ (`requirements-pymupdf4llm.txt`)
- `marker-pdf` — highest quality markdown conversion, Python 3.10+ (`requirements-marker.txt`)
- `docling` — IBM's layout-aware pipeline (tables, formulas, images), Python 3.10+ (`requirements-docling.txt`)
- `pdf2image` + `pytesseract` — OCR fallback for scanned PDFs (`requirements-ocr.txt`)
- System: `tesseract`, `poppler` (brew install on macOS, needed for OCR mode)
- System: `pandoc` (brew install on macOS, needed for EPUB conversion)
