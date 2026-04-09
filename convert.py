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
        # marker-pdf uses PEP 604 syntax (X | None) in its type hints, which
        # requires Python 3.10+. Fail early with a clear message rather than
        # surfacing a confusing TypeError from deep inside the import chain.
        if sys.version_info < (3, 10):
            raise DependencyError(
                "marker-pdf requires Python 3.10 or newer (current venv is "
                f"{sys.version_info.major}.{sys.version_info.minor}).\n"
                "  Either:\n"
                "    - Use the default pymupdf method (drop --papers / --method marker), or\n"
                "    - Create a Python 3.12 venv and reinstall: "
                "python3.12 -m venv .venv-marker && "
                ".venv-marker/bin/pip install marker-pdf"
            )
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


_WORD_ORDINALS = (
    r'first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth'
)
_EDITION_QUALIFIERS = (
    r'annotated|revised|reissue|updated|expanded|enlarged|new|'
    + _WORD_ORDINALS
)


def clean_title(stem):
    """Derive a clean book title from the PDF filename stem.

    Strips common trailing version markers (e.g. "4th Edition", "Annotated
    Edition", "V3") and any leftover punctuation from the separator that
    preceded them.
    """
    title = stem
    # Apply version-marker strippers repeatedly so compound patterns like
    # "3rd Annotated Edition" get fully removed.
    prev = None
    while prev != title:
        prev = title
        title = re.sub(r'\s*[Vv]\d+(\.\d+)?\s*$', '', title)
        title = re.sub(r'\s*\d+(st|nd|rd|th)\s+[Ee]dition\s*$', '', title)
        title = re.sub(
            r'\s*(?:' + _EDITION_QUALIFIERS + r')\s+[Ee]dition\s*$',
            '',
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r'\s*(?:' + _EDITION_QUALIFIERS + r')\s*$',
            '',
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r'\s*\([^)]*[Ee]dition[^)]*\)\s*$', '', title)
        # Strip trailing separator punctuation left behind by the strippers
        # (e.g. "Title, 4th Edition" -> "Title," -> "Title")
        title = re.sub(r'[,;:\-\s]+$', '', title)
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


# Curated wordlist for splitting joined all-caps headings. Focuses on
# words common in book titles: articles, prepositions, conjunctions, and
# vocabulary found on title pages / chapter headings.
_JOINED_CAPS_WORDS = frozenset(w.lower() for w in (
    # articles, prepositions, conjunctions, pronouns
    "a an the and or but of in on at by for to from with without into onto "
    "over under up down out off as is are was were be been being am i you "
    "we us our your their his her its this that these those if then than "
    "so not no yes all any some each every other another such which who "
    "what when where why how also"
).split() + [
    # title-page vocabulary
    "annotated", "revised", "updated", "expanded", "enlarged", "edition",
    "introduction", "foreword", "preface", "acknowledgments", "contents",
    "chapter", "part", "section", "appendix", "index", "bibliography",
    "copyright", "published", "volume", "series", "reissue", "first",
    "second", "third", "fourth", "fifth", "complete", "abridged",
    "unabridged", "illustrated", "author", "authors", "editor", "editors",
    "translated", "translator", "publisher",
    # common book / management title words
    "human", "side", "enterprise", "management", "leadership", "organization",
    "organizations", "organizational", "behavior", "science", "business",
    "history", "culture", "economy", "economics", "theory", "practice",
    "principles", "method", "methods", "system", "systems", "model",
    "models", "analysis", "study", "research", "guide", "handbook",
    "overview", "fundamentals", "essentials", "foundations", "thinking",
    "decision", "making", "strategy", "strategic", "tactical", "innovation",
    "design", "development", "growth", "change", "transition", "work",
    "workplace", "team", "teams", "group", "groups", "people", "person",
    "leader", "leaders", "manager", "managers", "founder", "founders",
    "company", "companies", "corporation", "project", "process", "product",
    "quality", "productivity", "performance", "operations", "crisis",
    "modern", "contemporary", "global", "local", "drive", "motivate",
    "motivation", "inspire", "inspiration", "purpose", "new", "old",
    # proper nouns commonly appearing in title pages
    "mcgregor", "deming", "pink", "daniel", "douglas", "edwards",
])


def _segment_joined_caps(word):
    """Split a run of joined letters into dictionary words via DP.

    Returns a list of segments if a valid segmentation is found, else None.
    A valid segmentation uses only words from the curated list, prefers
    fewer segments, and requires at least two segments.
    """
    n = len(word)
    if n < 6:
        return None

    lower = word.lower()
    # dp[i] = (segment_count, prev_index, matched_segment) for best split of word[:i]
    dp = [None] * (n + 1)
    dp[0] = (0, -1, None)

    for i in range(1, n + 1):
        # Try every possible previous boundary j < i where word[j:i] is a word.
        for j in range(max(0, i - 15), i):
            if dp[j] is None:
                continue
            candidate = lower[j:i]
            if len(candidate) < 2:
                # Only allow 'a' and 'i' as standalone single-char words
                if candidate not in ("a", "i"):
                    continue
            if candidate not in _JOINED_CAPS_WORDS:
                continue
            count = dp[j][0] + 1
            if dp[i] is None or count < dp[i][0]:
                dp[i] = (count, j, word[j:i])

    if dp[n] is None:
        return None

    # Reconstruct
    segments = []
    idx = n
    while idx > 0:
        _, prev, seg = dp[idx]
        segments.append(seg)
        idx = prev
    segments.reverse()

    # Require at least two segments and at most one single-char segment
    if len(segments) < 2:
        return None
    if sum(1 for s in segments if len(s) == 1) > 1:
        return None
    return segments


def _split_joined_caps(text):
    """Split joined ALL-CAPS words on heading-like lines.

    PyMuPDF sometimes extracts letter-spaced (tracked-out) headings with
    spacing collapsed, producing "THEHUMANSIDE" from "T H E  H U M A N  S I D E".
    Finds short, mostly-uppercase lines containing a run of joined letters
    and splits them using a curated English wordlist.

    Only applies to lines that look like headings (short, standalone,
    mostly uppercase) to avoid corrupting body prose.
    """
    join_pattern = re.compile(r'\b[A-Z]{6,}\b')

    def _rewrite_line(line):
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            return line
        alpha_chars = [c for c in stripped if c.isalpha()]
        if not alpha_chars:
            return line
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio < 0.8:
            return line

        def _sub(match):
            word = match.group(0)
            segments = _segment_joined_caps(word)
            if segments is None:
                return word
            return ' '.join(segments)

        return join_pattern.sub(_sub, line)

    return '\n'.join(_rewrite_line(l) for l in text.split('\n'))


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
    text = _split_joined_caps(text)
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

    # Lines that start a list item should absorb their continuation lines
    # into the same paragraph (the PDF wraps them across physical lines).
    list_item_pattern = re.compile(r'^(\s*)(?:[-*]\s|\d+[\.\)]\s)')

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Headings, page markers, blockquotes, fences, etc. stay as-is.
        # List items are structural but still need continuation joining.
        if _is_structural_line(stripped) and not list_item_pattern.match(line):
            result.append(line)
            i += 1
            continue

        # Start building a paragraph by joining continuation lines
        while i + 1 < len(lines):
            next_line = lines[i + 1]
            next_stripped = next_line.strip()

            # Stop joining at structural elements or blank lines (including
            # the next list item, which is itself structural)
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


def _detect_two_column_split(page):
    """Detect whether a page has a two-column layout.

    Returns the x-coordinate of the column gutter, or None if the page is
    a single column.

    Uses word-level bboxes (not blocks) so that the detection works even
    when PyMuPDF returns the entire body as a single merged block spanning
    both columns. Finds the x-position near the page midpoint where the
    highest fraction of rows have no word crossing through, and requires
    that fraction to be high (>= 65%). For a single-column page, body
    text spans the midpoint on most rows so no such gutter exists.
    """
    try:
        words = page.get_text("words")
    except Exception:
        return None
    if not words or len(words) < 30:
        return None
    page_width = page.rect.width
    mid = page_width / 2

    # Group words into rows, clustering y values within a tolerance so
    # that words on the same visual line (with minor baseline variation)
    # merge into one row. Without this, a single full-width line can split
    # into two "rows" that each have only partial x coverage, producing
    # false-positive gutters in single-column layouts.
    clean = [
        (w[0], w[1], w[2]) for w in words
        if len(w) >= 5 and isinstance(w[4], str) and w[4].strip()
    ]
    if not clean:
        return None
    clean.sort(key=lambda w: w[1])
    rows = []  # list of (y, [(x0, x1), ...])
    row_tol = 3.0
    for x0, y, x1 in clean:
        if rows and abs(y - rows[-1][0]) <= row_tol:
            rows[-1][1].append((x0, x1))
        else:
            rows.append((y, [(x0, x1)]))
    if len(rows) < 8:
        return None

    # Scan a window near the midpoint for the x with the best "no crossing"
    # coverage. Step in small increments so we can locate the gutter precisely
    # (body column gaps are often only 6-12pt wide). Require high coverage
    # (>= 75% of rows), AND require both sides to have substantial content so
    # we don't mistake a single-column layout (where most rows happen to end
    # before the midpoint due to ragged-right flush) for two columns.
    window = page_width * 0.15
    step = 2.0
    best_x = None
    best_coverage = 0
    x = mid - window
    while x <= mid + window:
        count = 0
        for _, intervals in rows:
            if not any(ix0 < x < ix1 for ix0, ix1 in intervals):
                count += 1
        if count > best_coverage:
            best_coverage = count
            best_x = x
        x += step

    if best_x is None:
        return None
    if best_coverage / len(rows) < 0.75:
        return None

    # Two-column pages come in two flavors:
    #
    # (1) "Synchronized": rows contain content from BOTH columns at the
    #     same y (e.g. argyris1977 body where PyMuPDF merges the columns
    #     into one block and we get words from both sides on every row).
    #     Signal: rows have a clean horizontal gap at the gutter.
    #
    # (2) "Staggered": each visual row is entirely in one column, but the
    #     columns are separate blocks stacked at different y-ranges (e.g.
    #     argyris1955 p4 where PyMuPDF gives us distinct left-col and
    #     right-col blocks). Signal: many rows live wholly in the left
    #     half, many rows live wholly in the right half.
    #
    # Accept if either signal is strong. Reject only when neither holds,
    # which correctly rules out 1-column pages with ragged-right lines
    # (book indexes, bibliographies) where the right half is empty.
    sync_rows = sum(
        1 for _, intervals in rows
        if _row_has_gutter_gap(intervals, best_x, min_gap_width=6)
    )
    left_only_rows = sum(
        1 for _, intervals in rows
        if intervals and all(ix1 < best_x - 2 for ix0, ix1 in intervals)
    )
    right_only_rows = sum(
        1 for _, intervals in rows
        if intervals and all(ix0 > best_x + 2 for ix0, ix1 in intervals)
    )
    # "Any" counts: rows with at least one word left of / right of gutter.
    # Used for the asymmetric body+sidebar rule below.
    left_any_rows = sum(
        1 for _, intervals in rows
        if any(ix1 < best_x - 2 for ix0, ix1 in intervals)
    )
    right_any_rows = sum(
        1 for _, intervals in rows
        if any(ix0 > best_x + 2 for ix0, ix1 in intervals)
    )

    if sync_rows >= 6 and sync_rows / len(rows) >= 0.20:
        return best_x
    if (
        left_only_rows >= 5
        and right_only_rows >= 5
        and left_only_rows / len(rows) >= 0.15
        and right_only_rows / len(rows) >= 0.15
    ):
        return best_x
    # Asymmetric / body+sidebar layout (variant A): the main body is a
    # single wide column and a short author bio sits in the other column,
    # with the bio's y-range overlapping the body so some rows are
    # "synchronized". argyris1993 p.2 is the canonical case.
    if sync_rows >= 5 and (left_any_rows >= 20 or right_any_rows >= 20):
        return best_x
    # Asymmetric / body+sidebar layout (variant B): the bio is a dedicated
    # 3-8 line block in one column, the body fills the other column, and
    # the y-ranges don't align closely enough to produce many synchronized
    # rows. argyris1989 p.2 is the canonical case: Lo=4, Ro=38, sync=3.
    # Accept as long as both columns have at least 3 dedicated rows AND
    # one side has 25+ rows of content AND there's at least some sync
    # evidence (sync + smaller dedicated count >= 5). This still rejects
    # single-column ragged pages (e.g. book indexes) because those have
    # zero dedicated rows in the empty "right column".
    if (
        left_only_rows >= 3
        and right_only_rows >= 3
        and max(left_any_rows, right_any_rows) >= 25
        and sync_rows + min(left_only_rows, right_only_rows) >= 5
    ):
        return best_x
    return None


def _row_has_gutter_gap(intervals, gutter, min_gap_width=6):
    """Return True if `intervals` has a horizontal gap spanning `gutter`.

    Merges overlapping intervals, then looks for a pair of consecutive
    merged intervals where the gap between them straddles `gutter` and is
    at least `min_gap_width` points wide. This is the geometric signature
    of a column gutter: content ends on one side, whitespace crosses the
    gutter, content resumes on the other side.
    """
    if not intervals:
        return False
    sorted_ivs = sorted(intervals, key=lambda iv: iv[0])
    merged = [sorted_ivs[0]]
    for a, b in sorted_ivs[1:]:
        if a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        if gap_start < gutter < gap_end and (gap_end - gap_start) >= min_gap_width:
            return True
    return False


def _words_to_text(words):
    """Reconstruct text from PyMuPDF word tuples, grouping into lines by y.

    Words are (x0, y0, x1, y1, text, block_no, line_no, word_no). Lines are
    separated by '\\n' so downstream line-oriented cleanup (paragraph join,
    header stripping) continues to work.
    """
    if not words:
        return ""
    sorted_words = sorted(words, key=lambda w: (round(w[1]), w[0]))
    lines = []
    current_line = []
    current_y = None
    for w in sorted_words:
        wy = round(w[1])
        if current_y is None or abs(wy - current_y) > 2:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [w[4]]
            current_y = wy
        else:
            current_line.append(w[4])
    if current_line:
        lines.append(" ".join(current_line))
    return "\n".join(lines)


def _extract_page_text(page):
    """Extract text from a page, respecting two-column layouts.

    For single-column pages, returns the default top-to-bottom extraction.
    For two-column pages, processes each block:
      - Blocks that don't cross the column gutter (pure left or pure right)
        are emitted as-is.
      - Short blocks that cross the gutter are treated as full-width
        (title, heading, abstract) and emitted as-is.
      - Tall blocks that cross the gutter are "merged" body blocks where
        PyMuPDF failed to separate the columns. These are split at the word
        level: left-column words are emitted in y-order, then right-column
        words, restoring the proper reading order.
    Blocks are then sorted by (y_top, x_left) so headers, bylines, abstract,
    body, and footnotes appear in the correct order.
    """
    split = _detect_two_column_split(page)
    if split is None:
        return page.get_text()

    try:
        blocks = page.get_text("blocks")
        words = page.get_text("words")
    except Exception:
        return page.get_text()

    text_blocks = [
        b for b in blocks
        if len(b) >= 5 and isinstance(b[4], str) and b[4].strip()
    ]
    if not text_blocks:
        return page.get_text()

    # Partition blocks by role so we can keep each column contiguous.
    # PyMuPDF often fragments a 2-column page into one-line blocks per
    # column; sorting everything by (y, x) would interleave the columns
    # row-by-row and reproduce the very problem we're trying to avoid.
    # The correct reading order is: full-width headers, then all of the
    # left column top-to-bottom, then all of the right column top-to-bottom,
    # then full-width footers.
    MERGED_HEIGHT = 80
    GUTTER_TOL = 5

    left_col = []   # list of (y0, text) sorted by y0
    right_col = []
    full_width = []  # list of (y0, text) - short blocks spanning the gutter

    for b in text_blocks:
        x0, y0, x1, y1, btext = b[0], b[1], b[2], b[3], b[4]
        height = y1 - y0
        crosses = (x0 < split - GUTTER_TOL) and (x1 > split + GUTTER_TOL)

        if crosses and height > MERGED_HEIGHT:
            # Merged body block: split at the word level. Append the
            # resulting halves to the column buffers so they read in the
            # correct order alongside any genuine pure-left / pure-right
            # blocks on the same page.
            #
            # Filter by block_no (word[5]) rather than bounding box so we
            # don't double-count words that live in neighboring overlapping
            # blocks. For example, a drop-cap title block often has a bbox
            # that overlaps the first few rows of the body block; the drop
            # cap's own words belong to block_no N while the body belongs
            # to block_no M, so bbox-based filtering would pull in both.
            block_no = b[5] if len(b) > 5 else None
            block_words = [
                w for w in words
                if len(w) >= 6 and isinstance(w[4], str) and w[4].strip()
                and (block_no is None or w[5] == block_no)
            ]
            left_words = [w for w in block_words if w[0] < split]
            right_words = [w for w in block_words if w[0] >= split]
            left_text = _words_to_text(left_words)
            right_text = _words_to_text(right_words)
            if left_text:
                ly0 = min((w[1] for w in left_words), default=y0)
                left_col.append((ly0, left_text))
            if right_text:
                ry0 = min((w[1] for w in right_words), default=y0)
                right_col.append((ry0, right_text))
        elif crosses:
            # Short full-width block (title, heading, caption, footnote).
            full_width.append((y0, btext))
        elif x1 <= split + GUTTER_TOL:
            left_col.append((y0, btext))
        else:
            right_col.append((y0, btext))

    left_col.sort(key=lambda e: e[0])
    right_col.sort(key=lambda e: e[0])
    full_width.sort(key=lambda e: e[0])

    # Decide where each full-width block sits relative to column content.
    # Headers end before the earliest column content; footers start after
    # the latest column content; anything in between is "inline" and we
    # place it after the left column so it still appears before the right
    # column body (best-effort — full-width mid-page elements are rare).
    col_y_min = min((e[0] for e in left_col + right_col), default=None)
    col_y_max = None
    if left_col or right_col:
        col_y_max = max(
            max((e[0] for e in left_col), default=float('-inf')),
            max((e[0] for e in right_col), default=float('-inf')),
        )

    header_fw = []
    footer_fw = []
    inline_fw = []
    for y0, text in full_width:
        if col_y_min is None:
            header_fw.append((y0, text))
        elif y0 < col_y_min:
            header_fw.append((y0, text))
        elif col_y_max is not None and y0 > col_y_max:
            footer_fw.append((y0, text))
        else:
            inline_fw.append((y0, text))

    # Join entries with single newlines within each segment (so clean_text
    # can re-flow wrapped visual lines into paragraphs) but double newlines
    # between segments (so header, columns, and footer stay distinct).
    # PyMuPDF frequently returns one block per visual line on column pages;
    # if we used "\n\n" between blocks, every line would become its own
    # paragraph and clean_text's line-joining heuristic wouldn't fire.
    segments = []
    if header_fw:
        segments.append("\n".join(t.strip() for _, t in header_fw if t.strip()))
    if left_col:
        segments.append("\n".join(t.strip() for _, t in left_col if t.strip()))
    if inline_fw:
        segments.append("\n".join(t.strip() for _, t in inline_fw if t.strip()))
    if right_col:
        segments.append("\n".join(t.strip() for _, t in right_col if t.strip()))
    if footer_fw:
        segments.append("\n".join(t.strip() for _, t in footer_fw if t.strip()))
    return "\n\n".join(s for s in segments if s) + "\n"


def _strip_surrogates(text):
    """Remove lone UTF-16 surrogate code points from extracted text.

    Some PDFs store text that PyMuPDF surfaces with unpaired surrogates
    (U+D800..U+DFFF) -- this happens with overlong UTF-8 sequences or
    non-standard embedded fonts. These code points cannot be encoded as
    valid UTF-8, so they crash the output file write. Strip them.
    """
    if not text:
        return text
    return re.sub(r'[\ud800-\udfff]+', '', text)


_PAGE_POINTER_RE = re.compile(r'^(?:p\.?\s*)?\d+\s*$', re.IGNORECASE)


def _is_useful_toc(toc_entries):
    """Decide whether an embedded TOC is worth emitting in the output.

    Academic papers from JSTOR and similar services embed a fake TOC of
    bare page pointers ("p. 1", "p. 2", ...) plus the whole journal
    issue's article list. These have no value in the output markdown and
    waste tokens.

    Heuristics for rejection:
      - All entries point at page <= 0 (PDF anchor targets, not real pages)
      - More than half of entry titles match "p. N" page-pointer format
      - All entries are at level 1 and the document has fewer than 30 pages
        (short papers don't need a TOC at all)
    """
    if not toc_entries:
        return False

    # All zero/negative page targets = JSTOR-style anchor-only TOC
    real_page_count = sum(1 for e in toc_entries if e[2] > 0)
    if real_page_count == 0:
        return False

    # Count page-pointer-style titles
    pointer_count = 0
    for entry in toc_entries:
        title = _strip_surrogates(entry[1] or '')
        title = re.sub(r'[\t\u2003\u2002\u00a0]+', ' ', title).strip()
        if _PAGE_POINTER_RE.match(title):
            pointer_count += 1
    if pointer_count > len(toc_entries) / 2:
        return False

    return True


def _format_embedded_toc(toc_entries):
    """Format a fitz TOC (list of [level, title, page]) as markdown.

    Each entry is indented by level. Uses a non-numbered list so the output
    reads as a hierarchical outline. Normalizes any tab/ideographic spaces
    in titles (common in bookmarks that prefix chapter numbers) and strips
    unpaired surrogate code points that some PDFs produce. Entries with
    page-pointer-style titles ("p. 5") or non-positive page targets are
    dropped since they come from JSTOR-style anchor TOCs that aren't useful.
    """
    if not toc_entries:
        return ""
    lines = ["## Table of Contents", ""]
    emitted = 0
    for entry in toc_entries:
        # fitz returns [level, title, page] (3-tuple) or with extra dict (4)
        level = max(1, entry[0])
        title = entry[1]
        page = entry[2]
        title = _strip_surrogates(title)
        title = re.sub(r'[\t\u2003\u2002\u00a0]+', ' ', title).strip()
        if not title:
            continue
        # Skip bare page pointers and unresolved anchor targets
        if _PAGE_POINTER_RE.match(title):
            continue
        if page <= 0:
            continue
        indent = "  " * (level - 1)
        lines.append(f"{indent}- {title} (p. {page})")
        emitted += 1
    if emitted == 0:
        return ""
    lines.append("")
    return "\n".join(lines)


def _is_broken_toc_page(text):
    """Detect pages that consist mostly of mangled TOC entries.

    After text extraction + bullet normalization, dotted-leader TOC entries
    look like "- Title ... pagenum" or similar. If most non-empty lines on
    a page match this pattern, we classify it as a broken TOC page and
    skip it in favor of the embedded bookmark-based TOC.
    """
    non_empty = [l.strip() for l in text.split('\n') if l.strip()]
    if len(non_empty) < 5:
        return False

    # Patterns for TOC-like lines:
    #   "- Title ... 42"            (post-normalization)
    #   "Title ....... 42"          (raw dotted leader)
    #   "- Figure ... 1"            (list-of-figures fragments)
    #   "Chapter 1 ... 42"
    toc_line = re.compile(
        r'^(?:-\s+)?(?:.+?)\s+(?:\.{2,}|…)\s*\d+\s*$'
    )
    # Also match lines that are a label + trailing number with no leader
    #   "- Figure ... 7"
    label_num = re.compile(
        r'^-\s+(?:Figure|Table|Chapter|Part|Section)\s*\.*\s*\d+\s*$',
        re.IGNORECASE,
    )
    bare_label_num = re.compile(
        r'^-?\s*(?:Figure|Table|Chapter|Part|Section)\s+\d+\s*$',
        re.IGNORECASE,
    )

    matches = sum(
        1 for line in non_empty
        if toc_line.match(line) or label_num.match(line) or bare_label_num.match(line)
    )
    return matches / len(non_empty) >= 0.5


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

    # Extract embedded TOC (bookmark tree) before closing the doc.
    # This sidesteps pdf-text-extraction mangling of dotted-leader TOCs.
    try:
        toc_entries = doc.get_toc()
    except Exception as e:
        log.debug("Could not read embedded TOC: %s", e)
        toc_entries = []

    pages_with_text = 0
    two_col_pages = 0

    # First pass: extract all page texts. _extract_page_text detects
    # two-column layouts and extracts columns in reading order, which
    # prevents PyMuPDF from interleaving left/right columns mid-sentence
    # on journal-article pages.
    raw_pages = []
    for i in range(total_pages):
        page = doc[i]
        # Track how many pages look two-column so we can hint the user
        # toward --papers / marker-pdf for likely academic papers.
        if _detect_two_column_split(page) is not None:
            two_col_pages += 1
        text = _extract_page_text(page)
        # Strip any unpaired surrogate code points that PyMuPDF sometimes
        # surfaces from PDFs with overlong UTF-8 or non-standard font encodings
        text = _strip_surrogates(text)
        if text.strip():
            pages_with_text += 1
            raw_pages.append((i + 1, text.strip()))
        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{total_pages} pages...")

    doc.close()

    # Strip running headers/footers across all pages
    cleaned_pages = _strip_running_headers(raw_pages)

    skipped_toc_pages = 0

    # errors="replace" is a safety net for any surrogate chars that slip
    # through the explicit _strip_surrogates() calls above
    with open(output_file, "w", encoding="utf-8", errors="replace") as f:
        f.write(f"# {title}\n\n")
        f.write("*Converted from PDF*\n\n")
        f.write(f"*Source: {pdf_path.name}*\n\n")
        f.write("---\n\n")

        # Emit embedded TOC at the top if it's actually useful. JSTOR-style
        # per-page anchor TOCs and the issue's article list are suppressed.
        emit_toc = _is_useful_toc(toc_entries)
        if emit_toc:
            formatted = _format_embedded_toc(toc_entries)
            if formatted:
                f.write(formatted)
                f.write("\n---\n\n")
            else:
                emit_toc = False

        # Only skip broken-TOC pages in the front matter (first 10% of pages)
        # AND only when we actually have a replacement TOC to offer.
        # Back-of-book indexes share the same line pattern but contain
        # content the user needs for keyword lookup.
        toc_skip_cutoff = max(20, total_pages // 10)

        for page_num, text in cleaned_pages:
            cleaned = clean_text(text)
            cleaned = _format_headings(cleaned)
            cleaned = _format_toc(cleaned)
            # Skip blank pages (no content after cleaning)
            if not cleaned.strip():
                continue
            # Skip pages that are mostly mangled TOC entries -- the
            # embedded bookmark TOC replaces them. Restricted to front
            # matter so back-of-book indexes are preserved.
            if (emit_toc
                    and page_num <= toc_skip_cutoff
                    and _is_broken_toc_page(cleaned)):
                skipped_toc_pages += 1
                log.debug("Skipping broken TOC page %d", page_num)
                continue
            f.write(f"<!-- Page {page_num} -->\n\n")
            f.write(cleaned)
            f.write("\n\n")

    if skipped_toc_pages:
        print(f"  Replaced {skipped_toc_pages} broken TOC page(s) with embedded bookmark TOC")

    # Check if we got enough text to consider this a real conversion
    if total_pages > 0 and (pages_with_text / total_pages) < MIN_TEXT_RATIO:
        output_file.unlink(missing_ok=True)
        raise ConversionError(
            f"Only {pages_with_text}/{total_pages} pages had extractable text. "
            f"This PDF may be scanned. Try: --method ocr"
        )

    print(f"  -> {output_file}")

    # Hint: if this document looks like an academic paper (majority of pages
    # detect as two-column AND it's short enough to plausibly be a paper),
    # suggest --papers for users on Python 3.10+. We never auto-switch; the
    # user opts in explicitly to keep behavior predictable.
    if (
        total_pages > 0
        and total_pages <= 60
        and two_col_pages / total_pages >= 0.5
    ):
        py_ok = sys.version_info >= (3, 10)
        if py_ok:
            print(
                "  Note: this looks like an academic paper. For higher-quality "
                "output, try --papers (routes to marker-pdf)."
            )
        else:
            print(
                "  Note: this looks like an academic paper. --papers would use "
                "marker-pdf but requires Python 3.10+ (current: "
                f"{sys.version_info.major}.{sys.version_info.minor})."
            )
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

    with open(output_file, "w", encoding="utf-8", errors="replace") as f:
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
    # --papers routes academic papers through marker-pdf, which has much
    # better layout analysis than the default pymupdf path. Requires
    # Python 3.10+ (enforced by check_dependencies) because marker-pdf
    # uses PEP 604 type-hint syntax.
    parser.add_argument(
        "--papers",
        action="store_true",
        help="Shortcut for --method marker (for academic papers; requires Python 3.10+)",
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
        "--archive",
        action="store_true",
        help="After a successful conversion, move the source PDF from "
             "input/ into archive/ (created if missing). Failed conversions "
             "and --skip-existing skips are left in place.",
    )
    parser.add_argument(
        "--archive-dir",
        default="archive",
        help="Directory to move successfully-converted PDFs into when "
             "--archive is set (default: archive/)",
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

    if args.ocr and args.papers:
        print("Error: --ocr and --papers are mutually exclusive")
        sys.exit(1)
    if args.ocr:
        method = "ocr"
    elif args.papers:
        method = "marker"
    else:
        method = args.method

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
    converted_pdfs = []  # successfully converted source paths, for --archive

    for pdf in pdfs:
        if args.skip_existing:
            existing = output_dir / f"{pdf.stem}.md"
            if existing.exists():
                print(f"Skipping (already exists): {pdf.name}")
                skipped += 1
                continue

        if convert_pdf(pdf, output_dir, method=method, auto_ocr=args.auto_ocr):
            success += 1
            converted_pdfs.append(pdf)
        else:
            failed += 1
        print()

    parts = [f"{success} converted", f"{failed} failed"]
    if skipped:
        parts.append(f"{skipped} skipped")
    print(f"Done. {', '.join(parts)}.")

    # --archive: move successfully-converted PDFs into the archive dir.
    # Only runs on success; failed conversions stay in input/ so the user
    # can retry. Skip collisions by appending a timestamp suffix so we
    # never overwrite an existing archived file.
    if args.archive and converted_pdfs:
        archive_dir = Path(args.archive_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        collisions = 0
        for src in converted_pdfs:
            dest = archive_dir / src.name
            if dest.exists():
                # Preserve the existing archived copy by suffixing the
                # new one with a timestamp.
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                dest = archive_dir / f"{src.stem}.{ts}{src.suffix}"
                collisions += 1
            try:
                shutil.move(str(src), str(dest))
                moved += 1
            except Exception as e:
                print(f"  Archive failed for {src.name}: {e}")
        msg = f"Archived {moved} PDF(s) to {archive_dir}/"
        if collisions:
            msg += f" ({collisions} renamed to avoid collision)"
        print(msg)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
