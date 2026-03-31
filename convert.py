#!/usr/bin/env python3
"""
BookConvert - Convert PDF books to clean Markdown.

Three conversion methods:
  - pymupdf (default): Fast, reliable text extraction using PyMuPDF/fitz
  - marker: High-quality conversion using marker-pdf (requires Python 3.10+)
  - ocr: Tesseract OCR for scanned/image-based PDFs (slowest but handles images)

Usage:
    python convert.py input/MyBook.pdf
    python convert.py input/MyBook.pdf --output output/
    python convert.py input/MyBook.pdf --method ocr      # Force OCR for scanned PDFs
    python convert.py input/MyBook.pdf --method marker    # Use marker-pdf
    python convert.py input/                              # Convert all PDFs in a directory
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def check_dependencies(method):
    """Check that required tools are installed for the chosen method."""
    if method == "pymupdf":
        try:
            import fitz
        except ImportError:
            print("Missing dependency: PyMuPDF (pip install pymupdf)")
            sys.exit(1)

    elif method == "marker":
        try:
            subprocess.run(
                ["marker_single", "--help"],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            print("Missing dependency: marker-pdf (pip install marker-pdf)")
            sys.exit(1)

    elif method == "ocr":
        missing = []
        try:
            import pdf2image
        except ImportError:
            missing.append("pdf2image (pip install pdf2image)")
        try:
            import pytesseract
        except ImportError:
            missing.append("pytesseract (pip install pytesseract)")
        try:
            subprocess.run(["tesseract", "--version"], capture_output=True, timeout=10)
        except FileNotFoundError:
            missing.append("tesseract (brew install tesseract)")

        if missing:
            print("Missing dependencies:")
            for dep in missing:
                print(f"  - {dep}")
            sys.exit(1)


def clean_title(stem):
    """Derive a clean book title from the PDF filename stem."""
    # Remove version markers like "V3", "v2.1", "2nd edition", etc.
    title = re.sub(r'\s*[Vv]\d+(\.\d+)?\s*$', '', stem)
    title = re.sub(r'\s*\d+(st|nd|rd|th)\s+[Ee]dition\s*$', '', title)
    # Remove trailing parenthetical edition markers
    title = re.sub(r'\s*\([^)]*[Ee]dition[^)]*\)\s*$', '', title)
    return title.strip()


def convert_with_pymupdf(pdf_path, output_dir):
    """Convert a PDF using PyMuPDF (fitz) for text extraction."""
    import fitz

    print(f"Converting with PyMuPDF: {pdf_path.name}")
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    print(f"  {total_pages} pages")

    title = clean_title(pdf_path.stem)
    output_file = output_dir / f"{pdf_path.stem}.md"

    with open(output_file, "w") as f:
        f.write(f"# {title}\n\n")
        f.write("*Converted from PDF*\n\n")
        f.write(f"*Source: {pdf_path.name}*\n\n")
        f.write("---\n\n")

        for i in range(total_pages):
            text = doc[i].get_text()
            if text.strip():
                f.write(f"<!-- Page {i + 1} -->\n\n")
                f.write(text.strip())
                f.write("\n\n")
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{total_pages} pages...")

    doc.close()
    print(f"  -> {output_file}")
    return True


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
    for md_file in output_dir.rglob("*.md"):
        target = output_dir / f"{pdf_path.stem}.md"
        if md_file != target:
            md_file.rename(target)
        print(f"  -> {target}")
        return True

    print("  No output generated. Try --method ocr for scanned PDFs.")
    return False


def convert_with_ocr(pdf_path, output_dir):
    """Convert a scanned PDF using OCR (pdf2image + tesseract)."""
    print(f"Converting with OCR: {pdf_path.name}")

    from pdf2image import convert_from_path
    import pytesseract

    title = clean_title(pdf_path.stem)
    output_file = output_dir / f"{pdf_path.stem}.md"

    pages = convert_from_path(str(pdf_path), dpi=300)
    print(f"  Processing {len(pages)} pages...")

    with open(output_file, "w") as f:
        f.write(f"# {title}\n\n")
        f.write("*Converted from PDF using OCR*\n\n")
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


def convert_pdf(pdf_path, output_dir, method="pymupdf"):
    """Convert a single PDF to markdown."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if method == "ocr":
        return convert_with_ocr(pdf_path, output_dir)
    elif method == "marker":
        return convert_with_marker(pdf_path, output_dir)
    else:
        return convert_with_pymupdf(pdf_path, output_dir)


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
        "--method",
        "-m",
        choices=["pymupdf", "marker", "ocr"],
        default="pymupdf",
        help="Conversion method (default: pymupdf)",
    )
    # Keep --ocr as a shortcut for backwards compatibility
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Shortcut for --method ocr",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip dependency check",
    )

    args = parser.parse_args()
    method = "ocr" if args.ocr else args.method

    if not args.skip_check:
        check_dependencies(method)

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
        if convert_pdf(pdf, output_dir, method=method):
            success += 1
        else:
            failed += 1
        print()

    print(f"Done. {success} converted, {failed} failed.")


if __name__ == "__main__":
    main()
