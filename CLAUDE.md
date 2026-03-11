# BookConvert

This project converts PDF books to clean Markdown files for use in Claude Projects and other LLM tools.

## Workflow

1. User places PDF(s) in the `input/` directory
2. Run `python convert.py input/` to convert all PDFs, or `python convert.py input/MyBook.pdf` for a single file
3. For scanned/image-based PDFs, use `python convert.py input/MyBook.pdf --ocr`
4. Converted markdown files appear in `output/`

## When helping users

- If a conversion produces poor results (garbled text, missing content), suggest trying `--ocr` mode
- If OCR output needs cleanup, help the user clean up the markdown: fix obvious OCR errors, add proper headings, remove page artifacts
- Keep the markdown header format: title, "Converted from PDF" note, source filename, then `---` separator
- Use `<!-- Page N -->` comments to mark page boundaries

## Dependencies

- `marker-pdf` - primary converter for text-based PDFs
- `pdf2image` + `pytesseract` - OCR fallback for scanned PDFs
- System: `tesseract`, `poppler` (brew install on macOS)
