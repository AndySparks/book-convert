#!/usr/bin/env python3
"""
BookConvert - Convert PDF books to clean Markdown.

Uses Marker for text-based PDFs and Tesseract OCR for scanned PDFs.

Usage:
    python convert.py input/MyBook.pdf
    python convert.py input/MyBook.pdf --output output/
    python convert.py input/MyBook.pdf --ocr          # Force OCR mode for scanned PDFs
    python convert.py input/                          # Convert all PDFs in a directory
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def check_dependencies():
    """Check that required tools are installed."""
    missing = []

    # Check for marker
    try:
        subprocess.run(
            ["marker_single", "--help"],
            capture_output=True,
            timeout=10,
        )
    except FileNotFoundError:
        missing.append("marker-pdf (pip install marker-pdf)")

    # Check for tesseract (needed for OCR mode)
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, timeout=10)
    except FileNotFoundError:
        missing.append("tesseract (brew install tesseract)")

    if missing:
        print("Missing dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nRun the setup steps in README.md to install them.")
        sys.exit(1)


def is_scanned_pdf(pdf_path):
    """Heuristic: try marker first, fall back to OCR if output is mostly empty."""
    return False  # Default to marker; use --ocr flag to force OCR


def convert_with_marker(pdf_path, output_dir):
    """Convert a text-based PDF using Marker."""
    print(f"Converting with Marker: {pdf_path.name}")
    result = subprocess.run(
        ["marker_single", str(pdf_path), str(output_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Marker error: {result.stderr}")
        return False

    # Find the generated markdown file and rename it
    # Marker creates a subdirectory with the output
    for md_file in output_dir.rglob("*.md"):
        target = output_dir / f"{pdf_path.stem}.md"
        if md_file != target:
            md_file.rename(target)
        print(f"  -> {target}")
        return True

    print("  No output generated. Try --ocr for scanned PDFs.")
    return False


def convert_with_ocr(pdf_path, output_dir):
    """Convert a scanned PDF using OCR (pdf2image + tesseract)."""
    print(f"Converting with OCR: {pdf_path.name}")

    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        print("OCR dependencies not installed. Run:")
        print("  pip install pdf2image pytesseract")
        print("  brew install tesseract poppler")
        return False

    output_file = output_dir / f"{pdf_path.stem}.md"

    pages = convert_from_path(str(pdf_path), dpi=300)
    print(f"  Processing {len(pages)} pages...")

    with open(output_file, "w") as f:
        f.write(f"# {pdf_path.stem}\n\n")
        f.write(f"*Converted from PDF using OCR*\n\n")
        f.write(f"*Source: {pdf_path.name}*\n\n")
        f.write("---\n\n")

        for i, page in enumerate(pages, 1):
            text = pytesseract.image_to_string(page)
            if text.strip():
                f.write(f"<!-- Page {i} -->\n\n")
                f.write(text.strip())
                f.write("\n\n")
            if i % 10 == 0:
                print(f"  Processed {i}/{len(pages)} pages...")

    print(f"  -> {output_file}")
    return True


def add_header(md_path, pdf_name):
    """Add a standard header to converted markdown if not present."""
    content = md_path.read_text()
    if not content.startswith("# "):
        stem = Path(pdf_name).stem
        header = f"# {stem}\n\n"
        header += f"*Converted from PDF*\n\n"
        header += f"*Source: {pdf_name}*\n\n"
        header += "---\n\n"
        md_path.write_text(header + content)


def convert_pdf(pdf_path, output_dir, use_ocr=False):
    """Convert a single PDF to markdown."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if use_ocr:
        return convert_with_ocr(pdf_path, output_dir)
    else:
        return convert_with_marker(pdf_path, output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF books to clean Markdown."
    )
    parser.add_argument(
        "input",
        help="PDF file or directory of PDFs to convert",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="output",
        help="Output directory (default: output/)",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Use OCR mode for scanned PDFs (slower but handles image-based PDFs)",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip dependency check",
    )

    args = parser.parse_args()

    if not args.skip_check:
        check_dependencies()

    input_path = Path(args.input)
    output_dir = Path(args.output)

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        pdfs = [input_path]
    elif input_path.is_dir():
        pdfs = sorted(input_path.glob("*.pdf"))
        if not pdfs:
            print(f"No PDF files found in {input_path}")
            sys.exit(1)
        print(f"Found {len(pdfs)} PDF(s) to convert.\n")
    else:
        print(f"Not a PDF file or directory: {input_path}")
        sys.exit(1)

    success = 0
    failed = 0

    for pdf in pdfs:
        if convert_pdf(pdf, output_dir, use_ocr=args.ocr):
            success += 1
        else:
            failed += 1
        print()

    print(f"Done. {success} converted, {failed} failed.")


if __name__ == "__main__":
    main()
