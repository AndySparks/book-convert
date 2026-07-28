# BookConvert

Convert PDF and EPUB books to clean Markdown files for use in [Claude Projects](https://claude.ai), NotebookLM, and other LLM tools.

Conversion paths:
- **PyMuPDF** (PDF default): Fast, reliable text extraction that works on any Python 3.7+
- **pymupdf4llm** (PDF): Text + image extraction, optimized for LLM ingestion (requires Python 3.10+)
- **Marker** (PDF): High-quality markdown conversion (requires Python 3.10+)
- **Docling** (PDF): IBM's layout-aware pipeline (requires Python 3.10+)
- **OCR** (PDF): Tesseract OCR for scanned/image-based PDFs
- **Pandoc** (EPUB): Preserves the epub's chapter structure as markdown headings

## Setup

### Default install (text-only extraction)

```bash
git clone https://github.com/AndySparks/book-convert.git
cd book-convert
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs PyMuPDF plus `pyspellchecker` (a small pure-Python dictionary
used by the default-on cleanup pass) and gives you the default
text-extraction backend. Works on Python 3.7+.

### Optional backends (install into .venv-marker)

Higher-quality backends (`pymupdf4llm`, `marker-pdf`, `docling`) require
Python 3.10+. Install them into a separate `.venv-marker` so your default
venv stays small:

```bash
python3.12 -m venv .venv-marker
.venv-marker/bin/pip install -r requirements-marker.txt        # marker-pdf
.venv-marker/bin/pip install -r requirements-pymupdf4llm.txt   # pymupdf4llm
.venv-marker/bin/pip install -r requirements-docling.txt       # docling
```

### OCR backend

```bash
brew install tesseract poppler
pip install -r requirements-ocr.txt
```

### EPUB support

```bash
brew install pandoc
```

EPUB files route through pandoc regardless of `--method` selection.

## Usage

### Convert a single PDF or EPUB

```bash
python convert.py input/MyBook.pdf
python convert.py input/MyBook.epub    # EPUB -> markdown via pandoc
```

### Convert all PDFs and EPUBs in a directory

```bash
python convert.py input/
```

Directory mode picks up both `.pdf` and `.epub` files. The tool dispatches each one to the right toolchain automatically.

### Choose a conversion method

```bash
python convert.py input/MyBook.pdf --method pymupdf          # default, fast, text-only
python convert.py input/MyBook.pdf --method pymupdf4llm      # text + images, needs Py3.10+
python convert.py input/MyBook.pdf --method marker           # highest quality, slowest
python convert.py input/MyBook.pdf --method docling          # IBM's layout-aware pipeline
python convert.py input/ScannedBook.pdf --method ocr         # tesseract OCR
```

### Extract figures and images

```bash
python convert.py input/MyBook.pdf --extract-images
```

When `--extract-images` is set, the pymupdf backend renders figures,
diagrams, and embedded raster images as PNGs in a sibling directory
(`output/<stem>_assets/`) and inserts markdown image references into
the body text at the right page position.

### Page locators

Every locator-emitting backend writes one comment per page:

    <!-- page_pdf=59 page_printed=47 -->
    <!-- page_pdf=3 page_printed=none -->

`page_pdf` is the 1-based index of the page inside the PDF file. It is
always accurate, and is sparse — pages with no extractable text are
omitted.

`page_printed` is the page number **printed on the page**. It is the only
address valid for scholarly citation. It is `none` when the source carries
no printed page number, which is normal for ebook-derived PDFs and
universal for EPUB.

Never present a `page_pdf` value as a page number. The sidecar declares
which you have:

| `page_numbering` | Meaning | Backends |
|---|---|---|
| `printed` | Real page numbers were captured | `pymupdf`, when printed page numbers were actually found |
| `pdf_only` | PDF page index only | `pymupdf` (no printed page numbers found), `pymupdf4llm`, `ocr` |
| `none` | No locators emitted at all | `marker`, `pandoc` (EPUB), `docling` |

`pymupdf` is the only backend that can produce a citable page number, and it
decides between `printed` and `pdf_only` at runtime. The other five have a
fixed capability. Read `page_numbering` from the sidecar rather than
assuming it from the `--method` you asked for.

Where printed-page-number survival is sparse, `page_printed_offset` is
derived from the captured samples and used to fill the gaps — but only
when at least 3 arabic samples all agree
(`page_printed_offset_consistent: true`), and only for PDF pages that fall
between the first and last captured sample. A book that renumbers partway
through, or that has printed page numbers only in part of the text, gets no
interpolation (or interpolation clamped to that span) rather than invented
page numbers — and interpolation never produces a printed page number
below 1.

Check coverage after any conversion:

    jq '.page_numbering, .page_printed_coverage, .page_printed_offset_consistent' output/<Title>.report.json

### Post-conversion cleanup (on by default)

Every conversion runs a verbatim-safe cleanup pass over the emitted
markdown that repairs the extraction artifacts no backend fixes on its own:

- **Dropped-space joins** where a function word is glued to its neighbour
  (`thefrozen` → `the frozen`, `sucha` → `such a`). The joined form is never
  a real English word, so splitting *restores* the author's text.
- **Stray-consonant citation ghosts** (`—wWilliam Golding` → `—William Golding`).
- **Picture-text blocks**: a real Table of Contents rendered as a table is
  unwrapped and kept; OCR garble (ISBN barcodes, etc.) is dropped.

The pass is designed never to mangle a real word: it only splits at a
whitelisted function-word boundary, so British spellings (`colour`),
coinages (`givenness`), proper nouns, and quoted literary coinages
(Joyce's `moocow`) pass through untouched. What it changed is recorded in
the sidecar report under `cleanup`.

```bash
python convert.py input/MyBook.pdf              # cleanup runs automatically
python convert.py input/MyBook.pdf --no-clean   # skip it
```

The de-join step uses `pyspellchecker` (installed by `requirements.txt`). If
it is ever missing, cleanup degrades gracefully — the dictionary-free repairs
still run and a warning is recorded.

### Passing flags through to marker

The marker backend accepts extra flags via `--marker-args`, forwarded
verbatim to `marker_single`:

```bash
python convert.py input/MyBook.pdf --method marker --marker-args '--use_llm'
python convert.py input/MyBook.pdf --method marker --marker-args '--html_tables_in_markdown'
```

The two that matter for table-heavy books:

- `--use_llm` activates marker's LLM table processors, which fix merged
  headers and rows split across lines. It needs an LLM service
  configured (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or a local ollama
  endpoint) — see `marker_single --help` for `--llm_service`.
- `--html_tables_in_markdown` emits `<table>` with real `colspan` /
  `rowspan`. GFM markdown cannot express spanning header cells at all,
  so this is the only way to preserve a multi-level table header —
  at the cost of much less readable output.

Run `marker_single --help` for the full flag list.

### Sidecar conversion report

Every conversion writes a `<stem>.report.json` alongside the markdown
containing: method used, page count, OCR pages, extracted assets,
quality score, `cleaned`/`cleanup` stats, table counts, and any warnings.
Useful for inspecting a batch run:

```bash
jq '.method,.extracted_assets,.quality_score' output/*.report.json
```

**Table fidelity.** `table_captions_seen` counts `TABLE 9-1` style
captions in the output; `tables_emitted` counts the grids actually
produced. A wide gap means the captions survived but their grids
collapsed into prose — the failure a three-page spot-check will miss.
The report adds an explicit warning when captions outnumber grids.

```bash
jq '.tables_emitted, .table_captions_seen, .warnings' output/*.report.json
```

Note that the `ocr` (tesseract) backend has **no** table reconstruction
at all, so it reports `0` emitted against however many captions it read.
For a book with real tables, use `marker`.

**Heading fidelity (EPUB).** `headings_emitted` counts markdown headings in
the converted body — BookConvert's own title line is excluded, so `0` means
`0`. `heading_source` says where they came from:

| `heading_source` | Meaning |
|---|---|
| `semantic` | The epub carried real `<h1>`–`<h6>` tags. The normal case. |
| `nav` | The epub had none; headings were derived from `toc.ncx` / the EPUB 3 nav document. Authoritative and ordered. |
| `class-heuristic` | No headings *and* no usable nav; derived from chapter-ish CSS classes (`<p class="chaphead">`). Lower confidence — spot-check it. |
| `none` | No signal at all. The output has no structural addressing whatsoever. |

Both fields are `null` on the PDF backends, which do not measure them.
`null` means "not measured", which is a different claim from `0`.

```bash
jq '.heading_source, .headings_emitted' output/*.report.json
```

This matters more for EPUB than for PDF: an epub is reflowable, so
`page_numbering` is always `none` and headings are the *only* address the
file has. `heading_source: "none"` on an epub means you have a text blob.

### Archive source PDFs after conversion

```bash
python convert.py input/ --archive                    # Move converted books into archive/
python convert.py input/ --archive --archive-dir old/ # Custom archive location
```

Failed conversions and `--skip-existing` skips are left in `input/`. Name collisions in the archive are preserved by appending a timestamp to the new copy. Both PDFs and EPUBs archive through the same flag.

### Skip already-converted files

```bash
python convert.py input/ --skip-existing
```

### Specify output directory

```bash
python convert.py input/MyBook.pdf --output output/Philosophy/
```

## How it works

1. Drop your PDF(s) or EPUB(s) into the `input/` folder
2. Run `convert.py` -- PDFs go through **PyMuPDF** by default, EPUBs go through **pandoc**
3. For text + image extraction, use `--method pymupdf4llm` (requires Python 3.10+)
4. For higher-quality PDF formatting, use `--method marker` or `--papers` (requires Python 3.10+)
5. For IBM's layout-aware pipeline, use `--method docling` (requires Python 3.10+)
6. For scanned books (where the pages are images), use `--method ocr` or `--ocr`
7. Converted markdown appears in `output/`, with a `<stem>.report.json` sidecar alongside each file

### EPUB conversion

EPUBs go through pandoc with raw HTML disabled, which gives you clean chapter headings, preserved emphasis, and usable footnote anchors without the publisher layout scaffolding leaking into the output. The `--method` flag is PDF-only; EPUBs always use pandoc. Install with `brew install pandoc`.

**Headings when the epub has none.** Pandoc can only map headings the source
actually carries, and plenty of trade epubs style their chapter openers as
`<p class="chaphead">` rather than `<h1>`. Those books used to convert to a
single flat document with no warning — and because an epub is reflowable,
that leaves the file with no addressing of any kind. BookConvert now checks
for semantic `h1`–`h6` first and, finding none, derives headings from the
epub's own navigation (`toc.ncx` for EPUB 2, the nav document for EPUB 3),
mapping nav nesting to heading depth. A chapter-ish CSS-class heuristic is
the fallback to the fallback. The source file is never modified; a rewritten
copy is handed to pandoc from a temp directory. Whatever happened is
declared in the sidecar as `heading_source` + `headings_emitted` — see
[Sidecar conversion report](#sidecar-conversion-report). Implementation:
`epub_structure.py`.

### Academic papers

The PyMuPDF pipeline detects two-column layouts and reconstructs the reading order so journal articles don't come out with left and right columns interleaved. This works on clean two-column pages, merged-block pages where PyMuPDF returns both columns as one giant block, and body-plus-sidebar pages with an inset author bio. See `docs/paper-extraction-research.md` and `docs/paper-extraction-decision.md` for the detection approach and the trade-offs vs. marker-pdf.

When `convert.py` sees a document that looks like a short, mostly-two-column paper, it prints a one-line hint suggesting `--papers` for higher-quality output (on Python 3.10+).

## Using with Claude Code

This project includes a `CLAUDE.md` file, so [Claude Code](https://docs.anthropic.com/en/docs/claude-code) understands the project and can help you convert and clean up books. Just open the project directory in Claude Code and ask it to help convert your PDFs.

## Running tests

The repo has a small pytest suite under `tests/`. To run it:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # first time only
python -m pytest tests/ -v
```

The tests cover the text quality scorer that gates the pymupdf → OCR
auto-fallback. See `docs/quality-fallback-design.md` for the design
behind that feature.

## Tips

- **Start with the default mode** (PyMuPDF). It's fast and works on any Python version.
- **Use `--method pymupdf4llm`** if you have Python 3.10+ and want text plus extracted images in the markdown.
- **Use `--method marker`** if you have Python 3.10+ and want the highest-quality markdown formatting.
- **Use `--method docling`** if you have Python 3.10+ and need IBM's layout-aware pipeline for complex layouts.
- **Use `--extract-images`** to pull figures and diagrams out as PNGs into an `_assets/` directory alongside the markdown.
- **Use `--auto-ocr`** to have the tool automatically retry with OCR when pymupdf fails. This catches both fully-scanned PDFs and PDFs with non-standard font encodings that produce garbled text (e.g. ligature artifacts like `n1ethod` for `method`). Without `--auto-ocr` you'll get an error message suggesting `--method ocr` and can re-run manually.
- **OCR output may need cleanup.** Claude Code can help you fix OCR artifacts, add proper headings, and improve formatting.
- **Inspect the sidecar report** (`output/<stem>.report.json`) after each conversion to check quality score, OCR page count, and any warnings.
- **Organize your output** into subdirectories by topic (e.g., `output/Coaching/`, `output/Writing/`) to keep things tidy.
- **Use `--skip-existing`** when re-running on a directory to avoid re-converting files you already have.

## Project structure

```
book-convert/
  input/                         <- Drop your PDFs here
  output/                        <- Converted markdown files appear here
  archive/                       <- Optional: --archive moves converted source PDFs here
  docs/                          <- Design notes (paper extraction research, decisions, results)
  convert.py                     <- Main conversion script
  requirements.txt               <- Default install (PyMuPDF only, Python 3.7+)
  requirements-marker.txt        <- marker-pdf extras (Python 3.10+)
  requirements-pymupdf4llm.txt   <- pymupdf4llm extras (Python 3.10+)
  requirements-docling.txt       <- docling extras (Python 3.10+)
  requirements-ocr.txt           <- OCR extras (tesseract + poppler required)
  requirements-dev.txt           <- Test dependencies
  CLAUDE.md                      <- Instructions for Claude Code
```

## License

MIT
