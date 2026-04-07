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
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

log = logging.getLogger("bookconvert")


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
            result = subprocess.run(
                ["marker_single", "--help"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise DependencyError(
                    "marker-pdf is installed but marker_single --help returned "
                    f"exit code {result.returncode}. Try reinstalling: pip install marker-pdf"
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


def _collapse_spaced_letters(text):
    """Collapse spaced-out letter artifacts back into words.

    PDF extraction sometimes produces headings like "H e a d i n g" from
    custom-spaced font rendering. Detects sequences of single letters
    separated by spaces and collapses them.
    """
    def _collapse_match(m):
        collapsed = m.group(0).replace(' ', '')
        # Only collapse if result is at least 3 chars (avoid false positives)
        if len(collapsed) >= 3:
            return collapsed
        return m.group(0)

    # Match sequences of single letters separated by 1-3 spaces (or thin/en spaces)
    # At least 4 single-letter groups to avoid false positives like "a b"
    text = re.sub(r'\b[A-Za-z](?:[\s\u2002\u2003\u2009]{1,3}[A-Za-z]){3,}\b', _collapse_match, text)
    return text


def _strip_running_headers(pages_text):
    """Detect and remove running headers and footers from page texts.

    Analyzes the first and last few lines of each page to find repeated
    patterns (book title, chapter name, page numbers) that appear across
    multiple pages. Strips them from the body text.

    Args:
        pages_text: list of (page_num, raw_text) tuples

    Returns:
        list of (page_num, cleaned_text) tuples
    """
    if len(pages_text) < 5:
        return pages_text

    # Collect the first few and last few lines from each page
    # to detect running headers/footers regardless of position
    from collections import Counter

    top_lines = []   # (normalized_line, raw_line) from top of each page
    bottom_lines = []

    def _normalize_header(line):
        """Strip page numbers and whitespace to find the repeating core."""
        s = re.sub(r'^\d+\s*', '', line)       # leading page number
        s = re.sub(r'\s*\d+$', '', s)           # trailing page number
        s = re.sub(r'\s*\|\s*\w*$', '', s)      # trailing "| page" (O'Reilly style)
        s = re.sub(r'^\w+\s*\|\s*', '', s)      # leading "page |" (O'Reilly style)
        return s.strip()

    for _, text in pages_text:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        # Check up to first 3 lines for header patterns
        for l in lines[:3]:
            top_lines.append(_normalize_header(l))
        # Check last 3 lines for footer patterns
        for l in lines[-3:]:
            bottom_lines.append(_normalize_header(l))

    top_counts = Counter(n for n in top_lines if n and len(n) > 3)
    bottom_counts = Counter(n for n in bottom_lines if n and len(n) > 3)

    # A header/footer pattern must appear on at least 15% of pages
    threshold = max(3, len(pages_text) * 0.15)

    header_patterns = {pat for pat, count in top_counts.items() if count >= threshold}
    footer_patterns = {pat for pat, count in bottom_counts.items() if count >= threshold}

    log.debug("Detected %d header pattern(s), %d footer pattern(s)",
              len(header_patterns), len(footer_patterns))
    for p in header_patterns:
        log.debug("  Header: %r", p)
    for p in footer_patterns:
        log.debug("  Footer: %r", p)

    # Also detect inline header patterns: "123 Book Title Text continues..."
    # where the page number + title is prepended to the first paragraph
    inline_header_patterns = set()
    for pat in header_patterns:
        if pat:
            inline_header_patterns.add(pat)
    # Also detect the book title from the majority of first-line content
    # even if it wasn't standalone (embedded in first paragraph)
    first_line_content = []
    for _, text in pages_text:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            first_line_content.append(lines[0])

    # Look for a common title prefix: "NNN Title Text rest of paragraph"
    title_prefix_counts = Counter()
    for line in first_line_content:
        # Try to extract "NNN Title Words" from start of line
        m = re.match(r'^(\d{1,4})\s+(.+?)(?:\s{2,}|\s+[A-Z][a-z])', line)
        if m:
            candidate = m.group(2).strip()
            if len(candidate) > 5:
                title_prefix_counts[candidate] += 1

    inline_title_prefixes = {
        pat for pat, count in title_prefix_counts.items()
        if count >= threshold
    }
    for p in inline_title_prefixes:
        log.debug("  Inline title prefix: %r (appears %d times)", p, title_prefix_counts[p])

    # Also detect standalone page-number lines (just a number, maybe with spaces)
    # Always strip these, even if no header/footer patterns were found
    standalone_pagenum = re.compile(r'^\s*\d{1,4}\s*$')
    # Also match standalone roman numeral page numbers (front matter)
    roman_pagenum = re.compile(
        r'^\s*[ivxlc]{1,7}\s*$', re.I
    )

    result = []
    for page_num, text in pages_text:
        lines = text.split('\n')
        cleaned = []
        for j, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue

            norm = _normalize_header(stripped)

            # Check position relative to page boundaries
            non_empty_indices = [k for k, l in enumerate(lines) if l.strip()]
            if not non_empty_indices:
                cleaned.append(line)
                continue
            pos_in_nonempty = non_empty_indices.index(j) if j in non_empty_indices else -1
            is_near_top = pos_in_nonempty >= 0 and pos_in_nonempty < 3
            is_near_bottom = pos_in_nonempty >= 0 and pos_in_nonempty >= len(non_empty_indices) - 3
            is_first = pos_in_nonempty == 0
            is_last = pos_in_nonempty == len(non_empty_indices) - 1

            # Strip if it matches a detected header pattern near top of page
            if is_near_top and norm in header_patterns:
                log.debug("  Stripping header on page %d: %r", page_num, stripped)
                continue
            # Strip if it matches a detected footer pattern near bottom of page
            if is_near_bottom and norm in footer_patterns:
                log.debug("  Stripping footer on page %d: %r", page_num, stripped)
                continue

            # Strip inline title prefix from first content line: "123 Book Title rest..."
            if is_near_top and inline_title_prefixes:
                for prefix in inline_title_prefixes:
                    pat = re.compile(r'^\d{1,4}\s+' + re.escape(prefix) + r'\s+')
                    m = pat.match(stripped)
                    if m:
                        stripped = stripped[m.end():]
                        line = stripped
                        log.debug("  Stripped inline header on page %d: prefix=%r", page_num, prefix)
                        break

            # Strip standalone page numbers (arabic or roman) at start/end of page
            if (is_near_top or is_near_bottom) and (
                standalone_pagenum.match(stripped) or roman_pagenum.match(stripped)
            ):
                continue

            # Strip "CHAPTER TITLE | page" or "page | BOOK TITLE" running headers
            # (common in O'Reilly and similar publishers)
            if (is_near_top or is_near_bottom) and re.match(
                r'^(?:\d{1,4}\s*\|\s*[A-Z].*|[A-Z][A-Z\s\',]+\|\s*\d{1,4})$', stripped
            ):
                log.debug("  Stripping pipe header/footer on page %d: %r", page_num, stripped)
                continue

            # Strip trailing page number appended to last line
            if is_last:
                line = re.sub(r'\s+\d{1,4}\s*$', '', line)

            cleaned.append(line)
        result.append((page_num, '\n'.join(cleaned)))

    return result


def _format_headings(text):
    """Detect and format section headings as markdown.

    Identifies heading patterns:
    - ALL-CAPS lines (short, standalone)
    - "Chapter N" / "Part N" patterns
    - Short standalone lines before body text
    """
    lines = text.split('\n')
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip empty lines and page markers
        if not stripped or stripped.startswith('<!-- Page'):
            result.append(line)
            continue

        # Already a markdown heading
        if stripped.startswith('#'):
            result.append(line)
            continue

        # "Chapter N" or "Part N" patterns -> ##
        # Max 10 words to avoid promoting full sentences like "Chapter 9 is a wildcard..."
        if (re.match(r'^(Chapter|CHAPTER|Part|PART)\s+(\d+|[IVXLC]+)', stripped, re.I)
                and len(stripped.split()) <= 10):
            result.append(f"## {stripped}")
            continue

        # ALL-CAPS lines that are likely headings (5-80 chars, mostly letters)
        # Only promote if the line is standalone: prev and next lines are
        # empty, page markers, or other structural elements (avoids false
        # positives from inline all-caps text like newspaper headlines)
        if (re.match(r'^[A-Z][A-Z\s\d:,\-&]{4,79}$', stripped)
                and len(stripped) < 80
                and sum(1 for c in stripped if c.isalpha()) > len(stripped) * 0.6):
            prev_stripped = lines[i - 1].strip() if i > 0 else ''
            next_stripped = lines[i + 1].strip() if i + 1 < len(lines) else ''
            prev_ok = (not prev_stripped or prev_stripped.startswith('<!-- Page')
                       or prev_stripped.startswith('#'))
            next_ok = (not next_stripped or next_stripped.startswith('<!-- Page')
                       or next_stripped.startswith('#'))
            if prev_ok or next_ok:
                if len(stripped) < 20:
                    result.append(f"### {stripped}")
                else:
                    result.append(f"## {stripped}")
                continue

        result.append(line)

    return '\n'.join(result)


def _format_toc(text):
    """Detect and reformat collapsed table of contents.

    TOC entries often get collapsed into single lines like:
    "Foreword ix Introduction xiii Chapter 1 1"
    This splits them back onto separate lines.
    """
    lines = text.split('\n')
    result = []

    for line in lines:
        stripped = line.strip()

        # Detect collapsed TOC: multiple "Title pagenum" pairs on one line
        # Pattern: word(s) followed by roman numeral or number, repeated 3+ times
        toc_pattern = re.compile(
            r'((?:[A-Z][A-Za-z\s\':,\-]+?)\s+'
            r'(?:[ivxlc]+|\d{1,3}))'
        )
        matches = toc_pattern.findall(stripped)
        if len(matches) >= 3 and len(stripped) > 60:
            # This looks like a collapsed TOC - split entries onto separate lines
            # Use a more precise split: title followed by page number
            entries = re.findall(
                r'([A-Z][A-Za-z\s\':,\-]+?)\s+((?:[ivxlc]+|\d{1,3}))(?=\s+[A-Z]|\s*$)',
                stripped
            )
            if len(entries) >= 3:
                for title, page in entries:
                    result.append(f"- {title.strip()} ... {page}")
                continue

        result.append(line)

    return '\n'.join(result)


def _normalize_bullets(text):
    """Convert Unicode bullet characters to standard markdown list items.

    Handles inline bullet runs (● Item 1 ● Item 2) by splitting them
    onto separate lines, and standalone bullet lines by normalizing the marker.
    """
    bullet_chars = r'[●•◆▪▸►‣⬥]'

    # Split inline bullet runs: "● Item 1 ● Item 2" -> separate lines
    # Only if there are 2+ bullets on the same line
    def _split_inline_bullets(m):
        line = m.group(0)
        items = re.split(r'\s*' + bullet_chars + r'\s*', line)
        items = [item.strip() for item in items if item.strip()]
        if len(items) >= 2:
            return '\n'.join(f'- {item}' for item in items)
        return line

    text = re.sub(
        r'^.*' + bullet_chars + r'.*' + bullet_chars + r'.*$',
        _split_inline_bullets,
        text,
        flags=re.MULTILINE,
    )

    # Normalize standalone bullet lines: "● Item" -> "- Item"
    text = re.sub(
        r'^(\s*)' + bullet_chars + r'\s*',
        r'\1- ',
        text,
        flags=re.MULTILINE,
    )

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
    # Fix ligatures, split words, missing spaces, spaced-out letters, and bullets
    text = _fix_ligatures(text)
    text = _fix_missing_spaces(text)
    text = _collapse_spaced_letters(text)
    text = _normalize_bullets(text)

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

    # First pass: extract all page texts
    raw_pages = []
    for i in range(total_pages):
        text = doc[i].get_text()
        if text.strip():
            pages_with_text += 1
            raw_pages.append((i + 1, text.strip()))
        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{total_pages} pages...")

    doc.close()

    # Strip running headers/footers across all pages
    cleaned_pages = _strip_running_headers(raw_pages)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write("*Converted from PDF*\n\n")
        f.write(f"*Source: {pdf_path.name}*\n\n")
        f.write("---\n\n")

        for page_num, text in cleaned_pages:
            cleaned = clean_text(text)
            cleaned = _format_headings(cleaned)
            cleaned = _format_toc(cleaned)
            # Skip blank pages (no content after cleaning)
            if not cleaned.strip():
                continue
            f.write(f"<!-- Page {page_num} -->\n\n")
            f.write(cleaned)
            f.write("\n\n")

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

        # Move any image directories that marker produced
        img_dirs = [d for d in tmp_path.rglob("*") if d.is_dir() and d.name == "images"]
        if not img_dirs:
            # Also check for any image files directly
            img_files = list(tmp_path.rglob("*.png")) + list(tmp_path.rglob("*.jpg"))
            if img_files:
                img_dest = output_dir / f"{pdf_path.stem}_images"
                img_dest.mkdir(exist_ok=True)
                for img in img_files:
                    shutil.move(str(img), str(img_dest / img.name))
                # Update image paths in the markdown
                content = target.read_text(encoding="utf-8")
                content = re.sub(
                    r'!\[([^\]]*)\]\((?:[^)]*/)([^)]+)\)',
                    rf'![\1]({pdf_path.stem}_images/\2)',
                    content
                )
                target.write_text(content, encoding="utf-8")
                print(f"  Moved {len(img_files)} image(s) to {img_dest}")
        else:
            for img_dir in img_dirs:
                img_dest = output_dir / f"{pdf_path.stem}_images"
                if img_dest.exists():
                    shutil.rmtree(str(img_dest))
                shutil.move(str(img_dir), str(img_dest))
                # Update image paths in the markdown
                content = target.read_text(encoding="utf-8")
                content = re.sub(
                    r'!\[([^\]]*)\]\((?:[^)]*/)([^)]+)\)',
                    rf'![\1]({pdf_path.stem}_images/\2)',
                    content
                )
                target.write_text(content, encoding="utf-8")
                print(f"  Moved images to {img_dest}")

        if len(md_files) > 1:
            log.warning("Marker produced %d .md files; only the first was used", len(md_files))

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
                    cleaned = clean_text(text.strip())
                    cleaned = _format_headings(cleaned)
                    cleaned = _format_toc(cleaned)
                    f.write(cleaned)
                    f.write("\n\n")
            if i % 10 == 0:
                print(f"  Processed {i}/{total_pages} pages...")

    print(f"  -> {output_file}")
    return True


def convert_pdf(pdf_path, output_dir, method="pymupdf", auto_ocr=False):
    """Convert a single PDF to markdown.

    Returns True on success, False on failure. Never raises.
    If auto_ocr is True and pymupdf/marker fails due to scanned content,
    automatically retries with OCR.
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
        if auto_ocr and method != "ocr" and "scanned" in str(e).lower():
            print(f"  Text extraction failed, auto-retrying with OCR...")
            try:
                check_dependencies("ocr")
                return convert_with_ocr(pdf_path, output_dir)
            except DependencyError as dep_e:
                print(f"  OCR fallback unavailable: {dep_e}")
                return False
            except Exception as ocr_e:
                partial = output_dir / f"{pdf_path.stem}.md"
                if partial.exists():
                    partial.unlink()
                print(f"  OCR fallback also failed: {ocr_e}")
                log.debug(traceback.format_exc())
                return False
        print(f"  FAILED: {e}")
        return False
    except Exception as e:
        # Clean up partial output on unexpected errors
        partial = output_dir / f"{pdf_path.stem}.md"
        if partial.exists():
            partial.unlink()
        print(f"  FAILED (unexpected): {e}")
        log.debug(traceback.format_exc())
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
        "--auto-ocr",
        action="store_true",
        help="Automatically retry with OCR if text extraction fails (scanned PDFs)",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip dependency check",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging output",
    )

    args = parser.parse_args()

    # Configure logging based on --verbose flag
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="  [%(levelname)s] %(message)s",
    )

    # Clean mode: process existing markdown files
    if args.clean:
        input_path = Path(args.input)
        if input_path.is_file() and input_path.suffix.lower() == ".md":
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

        if convert_pdf(pdf, output_dir, method=method, auto_ocr=args.auto_ocr):
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
