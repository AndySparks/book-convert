# BookConvert

This project converts PDF books to clean Markdown files for use in Claude Projects and other LLM tools.

**Spine status:** partially spined as of 2026-04-27. See `8-DECISIONS/2026-04-27-spine-adoption.md` for what travelled and what's an explicit divergence from the OS reference implementation. Spine vocabulary (the spine, spined, spine adoption, spine-native): `~/operating-system/8-DECISIONS/2026-04-27-spine-portability.md`.

**Read @1-ROADMAP.md** at session start for the rolling punch list of work in flight (Now / Next / Blocked / Someday). Renamed from `docs/TASKS.md` on 2026-04-27 for spine alignment. BookConvert does not carry a full `0-STRATEGY.md`; strategic context lives upstream in Management Craft's `docs/0-STRATEGY.md` under the MC Research Loop Acquire step.

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
8. EPUB files always route through pandoc regardless of `--method`
9. Add `--extract-images` (pymupdf backend only) to render figures, diagrams, and raster images as PNGs in a sibling `<stem>_assets/` dir with inline markdown references
10. Every conversion writes a `<stem>.report.json` sidecar: method, page counts, OCR pages, extracted assets, quality score, warnings
11. Converted markdown files appear in `output/`

## When helping users

- If a conversion produces poor results (garbled text, missing content), first try `--method pymupdf4llm` (Python 3.10+), then `--method ocr`; `--auto-ocr` auto-retries with tesseract/marker on quality failure
- For visually heavy books (diagrams, figures), use `--extract-images` or `--method pymupdf4llm` — both produce PNGs for figures
- If OCR output needs cleanup, help the user clean up the markdown: fix obvious OCR errors, add proper headings, remove page artifacts
- Keep the markdown header format: title, "Converted from PDF" note, source filename, then `---` separator
- Use `<!-- Page N -->` comments to mark page boundaries
- The `clean_title()` function strips version markers (e.g., "V3") from filenames for cleaner titles
- Inspect the `.report.json` sidecar to see what happened: `jq '.method,.extracted_assets,.quality_score' output/*.report.json`

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
5. **Note any improvement opportunities** for the BookConvert tool itself and offer to file them as GitHub issues on AndySparks/BookConvert

## Dependencies

Install layout: default `.venv` (Python 3.7+) for text extraction; `.venv-marker` (Python 3.10+) for the ML-backed extras.

- `pymupdf` — default converter, fast text extraction via PyMuPDF/fitz (`requirements.txt`)
- `pymupdf4llm` — PyMuPDF's LLM-oriented markdown exporter with image extraction, Python 3.10+ (`requirements-pymupdf4llm.txt`)
- `marker-pdf` — highest quality markdown conversion, Python 3.10+ (`requirements-marker.txt`)
- `docling` — IBM's layout-aware pipeline (tables, formulas, images), Python 3.10+ (`requirements-docling.txt`)
- `pdf2image` + `pytesseract` — OCR fallback for scanned PDFs (`requirements-ocr.txt`)
- System: `tesseract`, `poppler` (brew install on macOS, needed for OCR mode)
- System: `pandoc` (brew install on macOS, needed for EPUB conversion)
