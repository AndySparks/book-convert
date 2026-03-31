# BookConvert

Convert PDF books to clean Markdown files for use in [Claude Projects](https://claude.ai), NotebookLM, and other LLM tools.

Three conversion methods:
- **PyMuPDF** (default): Fast, reliable text extraction that works on any Python 3.7+
- **Marker**: High-quality markdown conversion (requires Python 3.10+)
- **OCR**: Tesseract OCR for scanned/image-based PDFs

## Setup

### 1. Clone and set up Python environment

```bash
git clone https://github.com/AndySparks/BookConvert.git
cd BookConvert
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs PyMuPDF (the default method). For OCR or Marker, install extras:

```bash
# OCR support (for scanned PDFs)
brew install tesseract poppler
pip install pdf2image pytesseract

# Marker support (requires Python 3.10+)
pip install marker-pdf
```

## Usage

### Convert a single PDF

```bash
python convert.py input/MyBook.pdf
```

### Convert all PDFs in a directory

```bash
python convert.py input/
```

### Choose a conversion method

```bash
python convert.py input/MyBook.pdf --method marker    # Use marker-pdf (needs Python 3.10+)
python convert.py input/ScannedBook.pdf --method ocr   # Use OCR for scanned PDFs
python convert.py input/ScannedBook.pdf --ocr          # Shortcut for --method ocr
```

### Skip already-converted files

```bash
python convert.py input/ --skip-existing
```

### Specify output directory

```bash
python convert.py input/MyBook.pdf --output output/Philosophy/
```

## How it works

1. Drop your PDF(s) into the `input/` folder
2. Run `convert.py` -- it uses **PyMuPDF** by default for fast, reliable text extraction
3. For higher-quality markdown formatting, use `--method marker` (requires Python 3.10+)
4. For scanned books (where the pages are images), use `--method ocr` or `--ocr`
5. Converted markdown appears in `output/`

## Using with Claude Code

This project includes a `CLAUDE.md` file, so [Claude Code](https://docs.anthropic.com/en/docs/claude-code) understands the project and can help you convert and clean up books. Just open the project directory in Claude Code and ask it to help convert your PDFs.

## Tips

- **Start with the default mode** (PyMuPDF). It's fast and works on any Python version.
- **Use `--method marker`** if you have Python 3.10+ and want richer markdown formatting.
- **Use `--ocr` only if** the default mode produces empty or garbled output -- this usually means the PDF is scanned/image-based. The tool will detect this and suggest OCR automatically.
- **OCR output may need cleanup.** Claude Code can help you fix OCR artifacts, add proper headings, and improve formatting.
- **Organize your output** into subdirectories by topic (e.g., `output/Coaching/`, `output/Writing/`) to keep things tidy.
- **Use `--skip-existing`** when re-running on a directory to avoid re-converting files you already have.

## Project structure

```
BookConvert/
  input/          <- Drop your PDFs here
  output/         <- Converted markdown files appear here
  convert.py      <- Main conversion script
  requirements.txt
  CLAUDE.md       <- Instructions for Claude Code
```

## License

MIT
