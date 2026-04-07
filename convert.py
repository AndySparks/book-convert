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
    python convert.py input/ --skip-existing              # Skip already-converted files
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class DependencyError(Exception):
    """Raised when a required dependency is missing."""
    pass


class ConversionError(Exception):
    """Raised when a conversion fails."""
    pass


def check_dependencies(method):
    """Check that required tools are installed for the chosen method.

    Raises DependencyError if anything is missing.
    """
    if method == "pymupdf":
        try:
            import fitz
        except ImportError:
            raise DependencyError("Missing dependency: PyMuPDF (pip install pymupdf)")

    elif method == "marker":
        try:
            subprocess.run(
                ["marker_single", "--help"],
                capture_output=True,
                timeout=10,
            )
        except FileNotFoundError:
            raise DependencyError("Missing dependency: marker-pdf (pip install marker-pdf)")

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
        # Check for Poppler (required by pdf2image for PDF rendering)
        try:
            subprocess.run(["pdftoppm", "-v"], capture_output=True, timeout=10)
        except FileNotFoundError:
            missing.append("poppler (brew install poppler)")

        if missing:
            lines = ["Missing dependencies:"]
            for dep in missing:
                lines.append(f"  - {dep}")
            raise DependencyError("\n".join(lines))


def clean_title(stem):
    """Derive a clean book title from the PDF filename stem."""
    title = re.sub(r'\s*[Vv]\d+(\.\d+)?\s*$', '', stem)
    title = re.sub(r'\s*\d+(st|nd|rd|th)\s+[Ee]dition\s*$', '', title)
    title = re.sub(r'\s*\([^)]*[Ee]dition[^)]*\)\s*$', '', title)
    return title.strip()


MIN_TEXT_RATIO = 0.1  # At least 10% of pages must have extractable text


def _is_structural_line(stripped):
    """Check if a line is a structural markdown element that should not be joined."""
    if not stripped:
        return True
    if stripped.startswith('<!-- Page'):
        return True
    if stripped.startswith('#'):
        return True
    if stripped.startswith('>'):
        return True
    if stripped.startswith('- ') or stripped.startswith('* '):
        return True
    if stripped.startswith('|'):
        return True
    if re.match(r'^\d+[\.\)]\s', stripped):
        return True
    if stripped.startswith('```') or stripped.startswith('---') or stripped.startswith('***'):
        return True
    # ALL-CAPS lines are likely headings
    if re.match(r'^[A-Z][A-Z\s]{5,}$', stripped):
        return True
    return False


def _fix_ligatures(text):
    """Replace PDF ligature characters and fix split-word artifacts.

    PDF extraction often produces ligature characters (fi, ff, fl, ffi, ffl)
    and sometimes splits the word around them with a space (e.g. "eﬀ ective"
    becomes "eff ective" after ligature replacement). This function handles
    both problems.
    """
    # Replace ligature characters (order matters: longer first)
    text = text.replace('\ufb03', 'ffi')
    text = text.replace('\ufb04', 'ffl')
    text = text.replace('\ufb01', 'fi')
    text = text.replace('\ufb00', 'ff')
    text = text.replace('\ufb02', 'fl')

    # Fix split-word artifacts: "fi rst" -> "first", "eff ective" -> "effective"
    text = re.sub(r'(\w*(?:fi|ff|fl))\s+([a-z]{1,8})\b', r'\1\2', text)

    # Fix "Th e" -> "The" (common ligature-adjacent artifact)
    text = re.sub(r'\bTh\s+e\b', 'The', text)
    text = re.sub(r'\bth\s+e\b', 'the', text)

    # Fix soft hyphens with following whitespace/newline
    text = re.sub(r'\u00ad\s*\n\s*', '', text)
    text = re.sub(r'\u00ad\s+', '', text)

    return text


# --- Missing-space fix for words jammed together by PDF extraction ---

_OFF_REAL = re.compile(
    r'^off(er|ers|ered|ering|erings|ice|ices|icer|icers|icial|ials|ially|'
    r'set|sets|line|end|ends|ended|ender|enders|ending|ense|enses|ensive|'
    r'spring|beat|hand|load|shore|side|stage|season|shoot|shoots|'
    r'ish|putting|ramp|screen|site|track|year)$', re.I
)
_STUFF_REAL = re.compile(r'^stuff(ed|ing|ings|s|y|ier|iest)$', re.I)
_SELF_REAL = re.compile(
    r'^self(ish|ishly|ishness|less|lessness|lessly|same|dom|hood)$', re.I
)


def _fix_missing_spaces(text):
    """Fix words jammed together by PDF extraction.

    PDF text extraction sometimes drops the space between words, especially
    after "off", "stuff", and "self" + following word. This function splits
    them: "offthe" -> "off the", "stuffin" -> "stuff in",
    "selfprotection" -> "self-protection".
    """
    def _fix_off(m):
        full = m.group(0)
        if _OFF_REAL.match(full):
            return full
        return 'off ' + full[3:]

    def _fix_stuff(m):
        full = m.group(0)
        if _STUFF_REAL.match(full):
            return full
        return 'stuff ' + full[5:]

    def _fix_self(m):
        full = m.group(0)
        if _SELF_REAL.match(full):
            return full
        return 'self-' + full[4:]

    text = re.sub(r'\boff[a-z]+', _fix_off, text)
    text = re.sub(r'\bstuff[a-z]+', _fix_stuff, text)
    text = re.sub(r'\bself[a-z]+', _fix_self, text)
    return text


def clean_text(text):
    """Post-process extracted text to fix common PDF conversion artifacts.

    Joins all lines within a paragraph into single long lines. A paragraph
    ends at a blank line, a structural element (heading, list, page marker,
    etc.), or a line that clearly starts a new paragraph (after sentence-ending
    punctuation on the previous line AND starts with uppercase).

    Also fixes ligatures, split-word artifacts, hyphenated word breaks, and
    soft hyphens. Preserves YAML frontmatter (between --- fences) untouched.
    """
    # Fix ligatures, split words, and missing spaces before line joining
    text = _fix_ligatures(text)
    text = _fix_missing_spaces(text)

    lines = text.split('\n')
    result = []
    i = 0

    # Skip YAML frontmatter if present
    if lines and lines[0].strip() == '---':
        result.append(lines[0])
        i = 1
        while i < len(lines):
            result.append(lines[i])
            if lines[i].strip() == '---':
                i += 1
                break
            i += 1

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Preserve structural lines as-is
        if _is_structural_line(stripped):
            result.append(line)
            i += 1
            continue

        # Start building a paragraph by joining continuation lines
        while i + 1 < len(lines):
            next_line = lines[i + 1]
            next_stripped = next_line.strip()

            # Stop joining at structural elements or blank lines
            if _is_structural_line(next_stripped):
                break

            # Stop joining if the current line ends a sentence AND
            # the next line starts a new one (uppercase after period)
            current_trimmed = line.rstrip()
            if (current_trimmed
                    and current_trimmed[-1] in '.!?"\u201d'
                    and next_stripped
                    and next_stripped[0].isupper()
                    and len(current_trimmed) > 40):
                break

            # Fix hyphenated word breaks
            if current_trimmed.endswith('-') and next_stripped and next_stripped[0].islower():
                line = current_trimmed[:-1] + next_stripped
            else:
                line = current_trimmed + ' ' + next_stripped
            i += 1

        result.append(line)
        i += 1

    return '\n'.join(result)


def convert_with_pymupdf(pdf_path, output_dir):
    """Convert a PDF using PyMuPDF (fitz) for text extraction.

    Raises ConversionError if the PDF appears to be scanned (too little text).
    """
    import fitz

    print(f"Converting with PyMuPDF: {pdf_path.name}")
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    print(f"  {total_pages} pages")

    title = clean_title(pdf_path.stem)
    output_file = output_dir / f"{pdf_path.stem}.md"

    pages_with_text = 0

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write("*Converted from PDF*\n\n")
        f.write(f"*Source: {pdf_path.name}*\n\n")
        f.write("---\n\n")

        for i in range(total_pages):
            text = doc[i].get_text()
            if text.strip():
                pages_with_text += 1
                f.write(f"<!-- Page {i + 1} -->\n\n")
                f.write(clean_text(text.strip()))
                f.write("\n\n")
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{total_pages} pages...")

    doc.close()

    # Check if we got enough text to consider this a real conversion
    if total_pages > 0 and (pages_with_text / total_pages) < MIN_TEXT_RATIO:
        output_file.unlink(missing_ok=True)
        raise ConversionError(
            f"Only {pages_with_text}/{total_pages} pages had extractable text. "
            f"This PDF may be scanned. Try: --method ocr"
        )

    print(f"  -> {output_file}")
    return True


def convert_with_marker(pdf_path, output_dir):
    """Convert a text-based PDF using Marker.

    Runs Marker in an isolated temp directory to avoid corrupting existing output.
    Raises ConversionError on failure.
    """
    print(f"Converting with Marker: {pdf_path.name}")

    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["marker_single", str(pdf_path), tmpdir],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ConversionError(f"Marker error: {result.stderr}")

        # Find the generated markdown in the temp directory
        tmp_path = Path(tmpdir)
        md_files = list(tmp_path.rglob("*.md"))
        if not md_files:
            raise ConversionError(
                "Marker produced no output. Try --method ocr for scanned PDFs."
            )

        # Move the first markdown file to the target location
        target = output_dir / f"{pdf_path.stem}.md"
        shutil.move(str(md_files[0]), str(target))
        print(f"  -> {target}")
        return True


def convert_with_ocr(pdf_path, output_dir):
    """Convert a scanned PDF using OCR (pdf2image + tesseract).

    Processes pages one at a time to avoid loading all images into memory.
    Raises ConversionError on failure.
    """
    print(f"Converting with OCR: {pdf_path.name}")

    from pdf2image import convert_from_path, pdfinfo_from_path
    import pytesseract

    title = clean_title(pdf_path.stem)
    output_file = output_dir / f"{pdf_path.stem}.md"

    # Get page count first, then process one page at a time
    info = pdfinfo_from_path(str(pdf_path))
    total_pages = info["Pages"]
    print(f"  {total_pages} pages")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write("*Converted from PDF using OCR*\n\n")
        f.write(f"*Source: {pdf_path.name}*\n\n")
        f.write("---\n\n")

        for i in range(1, total_pages + 1):
            # Convert one page at a time to keep memory bounded
            images = convert_from_path(
                str(pdf_path), dpi=300, first_page=i, last_page=i
            )
            if images:
                text = pytesseract.image_to_string(images[0])
                if text.strip():
                    f.write(f"<!-- Page {i} -->\n\n")
                    f.write(text.strip())
                    f.write("\n\n")
            if i % 10 == 0:
                print(f"  Processed {i}/{total_pages} pages...")

    print(f"  -> {output_file}")
    return True


def convert_pdf(pdf_path, output_dir, method="pymupdf"):
    """Convert a single PDF to markdown.

    Returns True on success, False on failure. Never raises.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if method == "ocr":
            return convert_with_ocr(pdf_path, output_dir)
        elif method == "marker":
            return convert_with_marker(pdf_path, output_dir)
        else:
            return convert_with_pymupdf(pdf_path, output_dir)
    except ConversionError as e:
        print(f"  FAILED: {e}")
        return False
    except Exception as e:
        # Clean up partial output on unexpected errors
        partial = output_dir / f"{pdf_path.stem}.md"
        if partial.exists():
            partial.unlink()
        print(f"  FAILED (unexpected): {e}")
        return False


def collect_pdfs(input_path):
    """Collect PDF files from a path (file or directory).

    Handles both .pdf and .PDF extensions in directory mode.
    """
    input_path = Path(input_path)

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    elif input_path.is_dir():
        pdfs = sorted(
            p for p in input_path.iterdir()
            if p.is_file() and p.suffix.lower() == ".pdf"
        )
        if not pdfs:
            print(f"No PDF files found in {input_path}")
            sys.exit(1)
        print(f"Found {len(pdfs)} PDF(s) to convert.\n")
        return pdfs
    else:
        print(f"Not a PDF file or directory: {input_path}")
        sys.exit(1)


def clean_markdown_file(md_path):
    """Apply clean_text to an existing markdown file in place.

    Preserves the header (everything before the first <!-- Page marker
    or the first blank line after ---).
    """
    md_path = Path(md_path)
    print(f"Cleaning: {md_path.name}")

    content = md_path.read_text(encoding="utf-8")
    before = content.count('\n')
    cleaned = clean_text(content)
    after = cleaned.count('\n')

    md_path.write_text(cleaned, encoding="utf-8")
    removed = before - after
    print(f"  {removed} lines joined ({before} -> {after})")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF books to clean Markdown."
    )
    parser.add_argument(
        "input",
        help="PDF file, markdown file, or directory to convert/clean",
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
        "--clean",
        action="store_true",
        help="Clean existing markdown file(s) -- fix orphaned lines and hyphenation. "
             "Pass a .md file or directory of .md files.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip PDFs that already have a markdown file in the output directory",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip dependency check",
    )

    args = parser.parse_args()

    # Clean mode: process existing markdown files
    if args.clean:
        input_path = Path(args.input)
        if input_path.is_file() and input_path.suffix == ".md":
            clean_markdown_file(input_path)
        elif input_path.is_dir():
            md_files = sorted(input_path.glob("*.md"))
            if not md_files:
                print(f"No .md files found in {input_path}")
                sys.exit(1)
            for md_file in md_files:
                clean_markdown_file(md_file)
            print(f"\nDone. Cleaned {len(md_files)} file(s).")
        else:
            print(f"Not a .md file or directory: {input_path}")
            sys.exit(1)
        sys.exit(0)

    method = "ocr" if args.ocr else args.method

    if not args.skip_check:
        try:
            check_dependencies(method)
        except DependencyError as e:
            print(e)
            sys.exit(1)

    output_dir = Path(args.output)
    pdfs = collect_pdfs(args.input)

    success = 0
    failed = 0
    skipped = 0

    for pdf in pdfs:
        if args.skip_existing:
            existing = output_dir / f"{pdf.stem}.md"
            if existing.exists():
                print(f"Skipping (already exists): {pdf.name}")
                skipped += 1
                continue

        if convert_pdf(pdf, output_dir, method=method):
            success += 1
        else:
            failed += 1
        print()

    parts = [f"{success} converted", f"{failed} failed"]
    if skipped:
        parts.append(f"{skipped} skipped")
    print(f"Done. {', '.join(parts)}.")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
