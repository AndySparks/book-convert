"""EPUB structural-heading recovery — pure zip/markup logic, no pandoc.

BookConvert routes EPUBs through pandoc on the premise that "pandoc maps
epub chapter structure to markdown headings." That premise holds only when
the EPUB actually carries semantic `<h1>`-`<h6>` tags. Plenty of trade
EPUBs style their chapter openers as `<p class="chaphead">` instead, and
pandoc has nothing to map: the whole book converts to one flat document.
Because EPUB is reflowable there are no page locators either, so such a
conversion ends up with no structural addressing of any kind — and it looks
identical to a good conversion in the sidecar.

This module detects that condition and recovers structure from the EPUB's
own navigation, which is authoritative and ordered:

* `toc.ncx` (EPUB 2) or the nav document (EPUB 3) gives an ordered,
  nested list of chapter labels and their anchor targets.
* Each nav entry is turned into an `<hN>` at its anchor inside the spine
  document, with nav nesting mapped to heading depth.
* A rewritten copy of the EPUB is handed to pandoc, which then has real
  headings to map.

A chapter-ish CSS class heuristic (`<p class="chaphead">`) is available as
a *secondary* fallback. Class names vary by publisher, so it is lower
confidence and never overrides the nav.

Nothing here mutates the source EPUB; `rewrite_epub` writes a new zip.
"""
from __future__ import annotations

import html
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

# Heading-source labels written to the sidecar. Kept as module constants so
# convert.py and the tests agree on the spelling.
SOURCE_SEMANTIC = "semantic"
SOURCE_NAV = "nav"
SOURCE_CLASS = "class-heuristic"
SOURCE_NONE = "none"

MAX_HEADING_LEVEL = 6

# --- low-level markup helpers -------------------------------------------
#
# Everything below parses with regex rather than ElementTree on purpose.
# Real-world EPUB XHTML routinely carries undeclared entities (`&nbsp;`)
# and inconsistent namespace prefixes that make a strict XML parse throw.
# We only ever need attribute values and nesting depth, and a failed parse
# here would silently cost the book its structure.

_ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*("([^"]*)"|'([^']*)')""")
_TAG_RE = re.compile(r"<[^>]+>")
_SEMANTIC_HEADING_RE = re.compile(r"<h[1-6](?=[\s/>])", re.IGNORECASE)
_BODY_OPEN_RE = re.compile(r"<body\b[^>]*>", re.IGNORECASE)
_XHTML_SUFFIXES = (".xhtml", ".html", ".htm", ".xht")

# Block-level containers we are willing to hoist a heading in front of when
# the nav anchor lands on an inline element (`<a id="c1"/>` inside a `<p>`).
_BLOCK_OPEN_RE = re.compile(
    r"<(p|div|section|blockquote|li|td|h[1-6])\b[^>]*>", re.IGNORECASE
)
_INLINE_TAGS = {"a", "span", "em", "i", "b", "strong", "small", "sup", "sub"}
_REPLACEABLE_TAGS = {"p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6"}


def _attrs(tag_text: str) -> Dict[str, str]:
    """Parse a start tag's attributes into a lowercased-key dict."""
    out = {}
    for m in _ATTR_RE.finditer(tag_text):
        value = m.group(3) if m.group(3) is not None else m.group(4)
        out[m.group(1).lower()] = value
    return out


def _text_of(markup: str) -> str:
    """Strip tags and collapse whitespace, yielding the visible text."""
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", markup))).strip()


def _normalize(text: str) -> str:
    """Fold a label for comparison: casefold, collapse space, drop punctuation
    that publishers add or drop inconsistently between nav and body."""
    text = re.sub(r"[\s ]+", " ", text).strip().lower()
    return re.sub(r"[^\w ]+", "", text).strip()


def has_semantic_headings(markup: str) -> bool:
    """True if the markup contains any `<h1>`-`<h6>` tag."""
    return _SEMANTIC_HEADING_RE.search(markup) is not None


def count_markdown_headings(text: str) -> int:
    """Count ATX headings (`# ` .. `###### `) outside fenced code blocks."""
    count = 0
    fence = None
    for line in text.splitlines():
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            continue
        if re.match(r"^#{1,6}\s+\S", line):
            count += 1
    return count


# --- EPUB container model -----------------------------------------------


@dataclass
class NavEntry:
    """One entry from the EPUB's own table of contents."""

    depth: int          # 1-based nesting depth in the nav
    label: str          # human-readable chapter title
    doc: str            # zip entry name of the target spine document
    anchor: Optional[str] = None   # fragment id inside that document


@dataclass
class EpubStructure:
    """What we could learn about an EPUB's structure without converting it."""

    spine: List[str] = field(default_factory=list)      # ordered zip names
    docs: Dict[str, str] = field(default_factory=dict)  # zip name -> markup
    nav: List[NavEntry] = field(default_factory=list)
    semantic: bool = False


def _resolve(base_dir: str, href: str) -> Tuple[str, Optional[str]]:
    """Resolve an href relative to `base_dir` into (zip name, anchor)."""
    href = unquote(href.strip())
    anchor = None
    if "#" in href:
        href, anchor = href.split("#", 1)
        anchor = anchor or None
    if not href:
        return "", anchor
    joined = posixpath.join(base_dir, href) if base_dir else href
    return posixpath.normpath(joined).lstrip("/"), anchor


def _zip_text(zf: zipfile.ZipFile, name: str) -> Optional[str]:
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return None


def _find_opf(zf: zipfile.ZipFile) -> Optional[str]:
    container = _zip_text(zf, "META-INF/container.xml")
    if container:
        for m in re.finditer(r"<rootfile\b[^>]*>", container, re.IGNORECASE):
            path = _attrs(m.group(0)).get("full-path")
            if path:
                return posixpath.normpath(unquote(path)).lstrip("/")
    # Some malformed EPUBs ship no container.xml. Fall back to the first
    # .opf in the archive rather than giving up on the whole book.
    for name in zf.namelist():
        if name.lower().endswith(".opf"):
            return name
    return None


def _parse_ncx(markup: str, base_dir: str) -> List[NavEntry]:
    """Parse an EPUB 2 `toc.ncx` navMap into ordered, depth-tagged entries.

    Depth comes from `<navPoint>` nesting, tracked with a token scan rather
    than an XML parse (see the module note on entity-hostile sources).
    """
    entries: List[NavEntry] = []
    depth = 0
    token_re = re.compile(
        r"<navPoint\b[^>]*?(/?)>|</navPoint>|<navLabel\b.*?</navLabel>|<content\b[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )
    pending_label = None
    for m in token_re.finditer(markup):
        token = m.group(0)
        low = token[:10].lower()
        if low.startswith("<navpoint"):
            depth += 1
            pending_label = None
            if m.group(1):          # self-closing navPoint
                depth -= 1
        elif low.startswith("</navpoi"):
            depth = max(0, depth - 1)
            pending_label = None
        elif low.startswith("<navlabel"):
            pending_label = _text_of(token)
        elif low.startswith("<content"):
            src = _attrs(token).get("src")
            if src and pending_label:
                doc, anchor = _resolve(base_dir, src)
                if doc:
                    entries.append(
                        NavEntry(max(1, depth), pending_label, doc, anchor)
                    )
            pending_label = None
    return entries


def _parse_nav_doc(markup: str, base_dir: str) -> List[NavEntry]:
    """Parse an EPUB 3 nav document's `<nav epub:type="toc">` list."""
    # Isolate the toc nav; fall back to the first <nav> if none is typed.
    navs = [
        m for m in re.finditer(r"<nav\b[^>]*>(.*?)</nav>", markup,
                               re.IGNORECASE | re.DOTALL)
    ]
    chosen = None
    for m in navs:
        types = _attrs(m.group(0)[: m.group(0).find(">") + 1])
        epub_type = types.get("epub:type") or types.get("type") or ""
        if "toc" in epub_type.split():
            chosen = m.group(1)
            break
    if chosen is None and navs:
        chosen = navs[0].group(1)
    if chosen is None:
        return []

    entries: List[NavEntry] = []
    depth = 0
    token_re = re.compile(
        r"<ol\b[^>]*>|</ol>|<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL
    )
    for m in token_re.finditer(chosen):
        token = m.group(0)
        low = token[:4].lower()
        if low.startswith("<ol"):
            depth += 1
        elif low.startswith("</ol"):
            depth = max(0, depth - 1)
        else:
            open_tag = token[: token.find(">") + 1]
            href = _attrs(open_tag).get("href")
            label = _text_of(token)
            if href and label:
                doc, anchor = _resolve(base_dir, href)
                if doc:
                    entries.append(NavEntry(max(1, depth), label, doc, anchor))
    return entries


def read_structure(epub_path: Path) -> EpubStructure:
    """Read an EPUB's spine, nav, and semantic-heading status.

    Never raises on a malformed EPUB: a partial or empty EpubStructure means
    "we could not learn anything", and the caller falls back to the
    unmodified pandoc path.
    """
    structure = EpubStructure()
    try:
        zf = zipfile.ZipFile(epub_path)
    except (zipfile.BadZipFile, OSError):
        return structure

    with zf:
        opf_name = _find_opf(zf)
        if not opf_name:
            return structure
        opf = _zip_text(zf, opf_name)
        if not opf:
            return structure
        opf_dir = posixpath.dirname(opf_name)

        manifest: Dict[str, Dict[str, str]] = {}
        nav_item_id = None
        for m in re.finditer(r"<item\b[^>]*>", opf, re.IGNORECASE):
            attrs = _attrs(m.group(0))
            item_id = attrs.get("id")
            if not item_id or not attrs.get("href"):
                continue
            manifest[item_id] = attrs
            if "nav" in (attrs.get("properties") or "").split():
                nav_item_id = item_id

        spine_match = re.search(
            r"<spine\b[^>]*>(.*?)</spine>", opf, re.IGNORECASE | re.DOTALL
        )
        ncx_id = None
        spine_body = ""
        if spine_match:
            ncx_id = _attrs(
                spine_match.group(0)[: spine_match.group(0).find(">") + 1]
            ).get("toc")
            spine_body = spine_match.group(1)

        # An EPUB 3 nav document is usually IN the spine and usually carries
        # its own "<h1>Contents</h1>". Counting that as a semantic heading
        # would suppress the fallback on exactly the books that need it, so
        # the nav document is excluded from the spine we reason about.
        nav_doc_name = None
        if nav_item_id and nav_item_id in manifest:
            nav_doc_name, _ = _resolve(opf_dir, manifest[nav_item_id]["href"])

        for m in re.finditer(r"<itemref\b[^>]*>", spine_body, re.IGNORECASE):
            idref = _attrs(m.group(0)).get("idref")
            item = manifest.get(idref or "")
            if not item:
                continue
            name, _ = _resolve(opf_dir, item["href"])
            if name == nav_doc_name:
                continue
            media = (item.get("media-type") or "").lower()
            if "xhtml" not in media and not name.lower().endswith(_XHTML_SUFFIXES):
                continue
            markup = _zip_text(zf, name)
            if markup is None:
                continue
            structure.spine.append(name)
            structure.docs[name] = markup

        structure.semantic = any(
            has_semantic_headings(m) for m in structure.docs.values()
        )

        # EPUB 3 nav document first, then the EPUB 2 ncx. Whichever yields
        # entries wins; the nav is authoritative either way.
        for item_id, parser in ((nav_item_id, _parse_nav_doc),
                                (ncx_id, _parse_ncx)):
            if structure.nav or not item_id or item_id not in manifest:
                continue
            name, _ = _resolve(opf_dir, manifest[item_id]["href"])
            markup = _zip_text(zf, name)
            if markup:
                structure.nav = parser(markup, posixpath.dirname(name))

        if not structure.nav:
            # Last resort: a toc.ncx present in the archive but not wired
            # through the spine's `toc` attribute (seen in older exports).
            for name in zf.namelist():
                if name.lower().endswith(".ncx"):
                    markup = _zip_text(zf, name)
                    if markup:
                        structure.nav = _parse_ncx(
                            markup, posixpath.dirname(name)
                        )
                    break

    return structure


# --- heading injection ---------------------------------------------------


def _heading_html(level: int, label: str) -> str:
    level = max(1, min(MAX_HEADING_LEVEL, level))
    return "<h%d>%s</h%d>" % (level, html.escape(label, quote=False), level)


def _find_id(markup: str, anchor: str) -> Optional[re.Match]:
    pattern = re.compile(
        r"<([a-zA-Z][\w:.-]*)\b[^>]*?\sid\s*=\s*[\"']%s[\"'][^>]*>"
        % re.escape(anchor)
    )
    return pattern.search(markup)


def _element_span(markup: str, start_tag: re.Match) -> Optional[Tuple[int, str]]:
    """Return (end offset, inner markup) for a non-nested element, else None."""
    tag = start_tag.group(1)
    if start_tag.group(0).rstrip().endswith("/>"):
        return None
    close_re = re.compile(r"</%s\s*>" % re.escape(tag), re.IGNORECASE)
    open_re = re.compile(r"<%s\b" % re.escape(tag), re.IGNORECASE)
    close = close_re.search(markup, start_tag.end())
    if not close:
        return None
    if open_re.search(markup, start_tag.end(), close.start()):
        return None    # nested same-tag element; not safe to swallow
    return close.end(), markup[start_tag.end():close.start()]


def _enclosing_block(markup: str, pos: int) -> Optional[re.Match]:
    """Return the open tag of the block enclosing an inline anchor at `pos`.

    Injecting an `<h1>` inside a `<p>` produces legal XML but ugly output, so
    an inline anchor is resolved to its block and handled there instead.
    """
    best = None
    for m in _BLOCK_OPEN_RE.finditer(markup, 0, pos):
        best = m
    return best


def inject_nav_headings(markup: str, targets: List[NavEntry],
                        min_depth: int = 1) -> Tuple[str, int]:
    """Insert `<hN>` elements into one spine document for each nav target.

    Returns (new markup, headings inserted). When the anchor lands on an
    element whose visible text already *is* the nav label (the common
    `<p class="chaphead" id="c1">Chapter 1</p>` shape), that element is
    promoted in place rather than duplicated.
    """
    # (start, end, replacement) triples collected first, then applied
    # last-first so earlier offsets stay valid. start == end is an insertion.
    edits: List[Tuple[int, int, str]] = []
    body = _BODY_OPEN_RE.search(markup)
    body_pos = body.end() if body else 0

    def _promotable(match, label):
        """(start, end) if this element's text already IS the label."""
        span = _element_span(markup, match)
        if not span:
            return None
        text = _text_of(span[1])
        if text and _normalize(text) == _normalize(label):
            return match.start(), span[0]
        return None

    for entry in targets:
        label = entry.label.strip()
        if not label:
            continue
        level = max(1, entry.depth - min_depth + 1)
        heading = _heading_html(level, label)
        start, end = None, None

        if entry.anchor:
            match = _find_id(markup, entry.anchor)
            if match:
                tag = match.group(1).lower()
                if tag in _REPLACEABLE_TAGS:
                    promoted = _promotable(match, label)
                    if promoted:
                        start, end = promoted
                    else:
                        start = match.start()
                elif tag in _INLINE_TAGS:
                    # An empty `<a id="c1"/>` marker usually sits inside the
                    # styled paragraph that carries the chapter title. Promote
                    # that paragraph when its text is the label; otherwise put
                    # the heading in front of it, never inside it.
                    block = _enclosing_block(markup, match.start())
                    promoted = _promotable(block, label) if block else None
                    if promoted:
                        start, end = promoted
                    elif block:
                        start = block.start()
                    else:
                        start = match.start()
                else:
                    start = match.start()

        if start is None:
            start = body_pos
        edits.append((start, end if end is not None else start, heading))

    if not edits:
        return markup, 0

    # Apply highest offset first so earlier offsets stay valid. Ties (several
    # nav entries landing on the same insertion point) are applied in reverse
    # nav order, which leaves them in nav order in the output.
    ordered = sorted(
        enumerate(edits), key=lambda pair: (pair[1][0], pair[0]), reverse=True
    )
    inserted = 0
    for _, (start, end, heading) in ordered:
        markup = markup[:start] + heading + markup[end:]
        inserted += 1
    return markup, inserted


# Chapter-ish class tokens. Deliberately narrow: a false positive here turns
# body copy into a heading, which is worse than no heading at all.
_CLASS_STEM_RE = re.compile(r"chap|part|sect|division|book", re.IGNORECASE)
_CLASS_HEAD_RE = re.compile(r"head|title|hd|ttl", re.IGNORECASE)
_KNOWN_CLASS_TOKENS = {
    "chaphead", "chapterhead", "chaptitle", "chapter-title", "chap-title",
    "ct", "cn", "h1", "head1", "title1", "parttitle", "part-title",
}
_CLASS_PARA_RE = re.compile(
    r"<p\b([^>]*)>(.*?)</p>", re.IGNORECASE | re.DOTALL
)
_MAX_HEURISTIC_LABEL_CHARS = 120


def _class_tokens(attr_text: str) -> List[str]:
    value = _attrs("<p" + attr_text + ">").get("class") or ""
    return [t.lower() for t in value.split()]


def _is_chapterish(token: str) -> bool:
    if token in _KNOWN_CLASS_TOKENS:
        return True
    return bool(_CLASS_STEM_RE.search(token) and _CLASS_HEAD_RE.search(token))


def _heuristic_level(token: str) -> int:
    if "sub" in token or "sect" in token:
        return 2
    return 1


def pick_heuristic_class(docs: Dict[str, str]) -> Optional[str]:
    """Choose the single most-used chapter-ish `<p>` class across the book.

    Restricting to one class is the de-noiser: a publisher uses one class
    for chapter openers, so a book with three "chapter-ish" classes is a
    book where the heuristic is guessing.
    """
    counts: Dict[str, int] = {}
    for markup in docs.values():
        for m in _CLASS_PARA_RE.finditer(markup):
            text = _text_of(m.group(2))
            if not text or len(text) > _MAX_HEURISTIC_LABEL_CHARS:
                continue
            for token in _class_tokens(m.group(1)):
                if _is_chapterish(token):
                    counts[token] = counts.get(token, 0) + 1
    if not counts:
        return None
    return max(sorted(counts), key=lambda t: counts[t])


def inject_class_headings(markup: str, token: str) -> Tuple[str, int]:
    """Promote every `<p class="{token}">` in one document to a heading."""
    level = _heuristic_level(token)
    count = 0

    def repl(m):
        nonlocal count
        text = _text_of(m.group(2))
        if not text or len(text) > _MAX_HEURISTIC_LABEL_CHARS:
            return m.group(0)
        if token not in _class_tokens(m.group(1)):
            return m.group(0)
        count += 1
        return _heading_html(level, text)

    return _CLASS_PARA_RE.sub(repl, markup), count


# --- rewriting -----------------------------------------------------------


def rewrite_epub(src: Path, dest: Path, replacements: Dict[str, str]) -> None:
    """Copy `src` to `dest`, substituting the named entries' text.

    The `mimetype` entry is re-emitted first and uncompressed, as the EPUB
    spec requires — pandoc rejects the archive otherwise.
    """
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        dest, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        names = zin.namelist()
        ordered = [n for n in names if n == "mimetype"] + [
            n for n in names if n != "mimetype"
        ]
        for name in ordered:
            if name == "mimetype":
                zout.writestr(
                    zipfile.ZipInfo("mimetype"),
                    zin.read(name),
                    compress_type=zipfile.ZIP_STORED,
                )
            elif name in replacements:
                zout.writestr(name, replacements[name].encode("utf-8"))
            else:
                zout.writestr(zin.getinfo(name), zin.read(name))


@dataclass
class HeadingPlan:
    """The decision for one EPUB: where headings come from and how many."""

    source: str = SOURCE_NONE
    injected: int = 0
    replacements: Dict[str, str] = field(default_factory=dict)


def plan_headings(structure: EpubStructure) -> HeadingPlan:
    """Decide how to recover headings for an EPUB with no semantic ones.

    Nav first (authoritative, ordered), CSS-class heuristic second. Returns
    a plan with `source == SOURCE_NONE` when neither signal is available.
    """
    if structure.semantic:
        return HeadingPlan(source=SOURCE_SEMANTIC)

    by_doc: Dict[str, List[NavEntry]] = {}
    for entry in structure.nav:
        if entry.doc in structure.docs:
            by_doc.setdefault(entry.doc, []).append(entry)

    if by_doc:
        # Normalize depth so the shallowest nav level becomes <h1> even when
        # a nav document wraps everything in an extra <ol>.
        min_depth = min(e.depth for entries in by_doc.values() for e in entries)
        plan = HeadingPlan(source=SOURCE_NAV)
        for doc, entries in by_doc.items():
            markup, count = inject_nav_headings(
                structure.docs[doc], entries, min_depth=min_depth
            )
            if count:
                plan.replacements[doc] = markup
                plan.injected += count
        if plan.injected:
            return plan

    token = pick_heuristic_class(structure.docs)
    if token:
        plan = HeadingPlan(source=SOURCE_CLASS)
        for doc in structure.spine:
            markup, count = inject_class_headings(structure.docs[doc], token)
            if count:
                plan.replacements[doc] = markup
                plan.injected += count
        if plan.injected:
            return plan

    return HeadingPlan(source=SOURCE_NONE)


def prepare_epub(epub_path: Path, work_dir: Path) -> Tuple[Path, str, int]:
    """Return (path to convert, heading source, headings injected).

    When the EPUB already exposes semantic `h1`-`h6`, the original path is
    returned untouched — the normal pandoc path is not perturbed in any way.
    Otherwise a rewritten copy carrying derived `<hN>` tags is written into
    `work_dir` and returned in its place.
    """
    structure = read_structure(epub_path)
    if not structure.docs:
        # Unreadable or exotic container. Let pandoc try the original; it
        # reports its own errors better than we can guess at them.
        return epub_path, SOURCE_SEMANTIC if structure.semantic else SOURCE_NONE, 0

    plan = plan_headings(structure)
    if plan.source == SOURCE_SEMANTIC or not plan.replacements:
        return epub_path, plan.source, 0

    work_dir.mkdir(parents=True, exist_ok=True)
    dest = work_dir / epub_path.name
    rewrite_epub(epub_path, dest, plan.replacements)
    return dest, plan.source, plan.injected
