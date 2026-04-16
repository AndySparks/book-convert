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

This installs PyMuPDF only and gives you the default text-extraction
backend. Works on Python 3.7+.

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

### Sidecar conversion report

Every conversion writes a `<stem>.report.json` alongside the markdown
containing: method used, page count, OCR pages, extracted assets,
quality score, and any warnings. Useful for inspecting a batch run:

```bash
jq '.method,.extracted_assets,.quality_score' output/*.report.json
```

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
