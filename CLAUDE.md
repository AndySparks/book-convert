# BookConvert

This project converts PDF books to clean Markdown files for use in Claude Projects and other LLM tools.

## Workflow

1. User places PDF(s) in the `input/` directory
2. Run `python convert.py input/` to convert all PDFs, or `python convert.py input/MyBook.pdf` for a single file
3. Default method is `pymupdf` (fast, works on Python 3.7+)
4. Use `--method marker` for richer markdown (requires Python 3.10+)
5. Use `--method ocr` or `--ocr` for scanned/image-based PDFs
6. Converted markdown files appear in `output/`

## When helping users

- If a conversion produces poor results (garbled text, missing content), suggest trying `--method ocr`
- If OCR output needs cleanup, help the user clean up the markdown: fix obvious OCR errors, add proper headings, remove page artifacts
- Keep the markdown header format: title, "Converted from PDF" note, source filename, then `---` separator
- Use `<!-- Page N -->` comments to mark page boundaries
- The `clean_title()` function strips version markers (e.g., "V3") from filenames for cleaner titles

## Dependencies

- `pymupdf` - default converter, fast text extraction via PyMuPDF/fitz
- `marker-pdf` - high-quality markdown conversion (Python 3.10+ only)
- `pdf2image` + `pytesseract` - OCR fallback for scanned PDFs
- System: `tesseract`, `poppler` (brew install on macOS, needed for OCR mode)
