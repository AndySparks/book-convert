# BookConvert

Convert PDF books to clean Markdown files for use in [Claude Projects](https://claude.ai), NotebookLM, and other LLM tools.

Handles both text-based PDFs (using [Marker](https://github.com/VikParuchuri/marker)) and scanned/image-based PDFs (using OCR via Tesseract).

## Setup

### 1. Install system dependencies (macOS)

```bash
brew install tesseract poppler ghostscript
```

### 2. Clone and set up Python environment

```bash
git clone https://github.com/AndySparks/BookConvert.git
cd BookConvert
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

### Convert a scanned/image-based PDF (OCR mode)

```bash
python convert.py input/ScannedBook.pdf --ocr
```

### Specify output directory

```bash
python convert.py input/MyBook.pdf --output output/Philosophy/
```

## How it works

1. Drop your PDF(s) into the `input/` folder
2. Run `convert.py` — it uses **Marker** by default for text-based PDFs, which produces high-quality markdown
3. For scanned books (where the pages are images), use the `--ocr` flag — this uses **Tesseract** to extract text via OCR
4. Converted markdown appears in `output/`

## Using with Claude Code

This project includes a `CLAUDE.md` file, so [Claude Code](https://docs.anthropic.com/en/docs/claude-code) understands the project and can help you convert and clean up books. Just open the project directory in Claude Code and ask it to help convert your PDFs.

## Tips

- **Start with the default mode** (no `--ocr` flag). It's faster and produces better formatting for text-based PDFs.
- **Use `--ocr` only if** the default mode produces empty or garbled output — this usually means the PDF is scanned/image-based.
- **OCR output may need cleanup.** Claude Code can help you fix OCR artifacts, add proper headings, and improve formatting.
- **Organize your output** into subdirectories by topic (e.g., `output/Coaching/`, `output/Writing/`) to keep things tidy.

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
