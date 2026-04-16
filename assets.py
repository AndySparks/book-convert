"""Image region detection and rendering for BookConvert.

Extracts figures, diagrams, and raster images from PDF pages and renders
them as PNGs via clipped `page.get_pixmap`. The rendered assets get a
markdown image reference stitched into the page text by the pymupdf
backend.

Three sources feed the region list:
  1. Raster images embedded in the PDF (page.get_image_info()).
  2. Vector drawings clustered by bounding box (page.get_drawings()).
  3. Figure captions near the above regions (CAPTION_RE).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

import fitz


# Captions: "Figure 1", "Figure 6.1", "FIGURE 3", "Exhibit 2.4", "Diagram 5".
# Must appear at the start of a line-ish string. Requires a number after
# the label word so body-text sentences that happen to start with "Figure"
# don't match.
CAPTION_RE = re.compile(
    r"^\s*(?:figure|fig\.?|exhibit|diagram|chart)\s+\d+(?:[.\-]\d+)?\b",
    re.IGNORECASE,
)


# Minimum pixel area for a raster region to count. Tiny icons / logos /
# bullet decorations under this threshold are ignored.
MIN_IMAGE_AREA = 2000  # ~45x45 px at PDF native resolution


def find_raster_regions(page: fitz.Page) -> List[fitz.Rect]:
    """Return bounding boxes for embedded raster images on this page.

    Filters out tiny images (below MIN_IMAGE_AREA) that are almost always
    decorative: bullet glyphs, page decorations, imprint logos.
    """
    regions: List[fitz.Rect] = []
    try:
        # get_image_info returns dicts with 'bbox' key in PDF points.
        info = page.get_image_info(xrefs=True)
    except Exception:
        return []
    for item in info:
        bbox = item.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        rect = fitz.Rect(*bbox)
        if rect.is_empty or (rect.width * rect.height) < MIN_IMAGE_AREA:
            continue
        regions.append(rect)
    return regions


# Minimum vector-drawing cluster area. Single stroke-width lines (rules
# above/below headings, underlines, footnote separators) are tiny and
# never qualify.
MIN_VECTOR_AREA = 2500
# Two boxes cluster together if they overlap OR are within this many PDF
# points of each other.
VECTOR_CLUSTER_GAP = 30


def find_vector_regions(page: fitz.Page) -> List[fitz.Rect]:
    """Return bounding boxes for clustered vector drawings on this page.

    PyMuPDF's get_drawings returns one entry per drawing primitive
    (stroke, fill, rect). A figure is a cluster of primitives with
    overlapping or nearby bounding boxes. We merge until no more merges
    are possible, then drop clusters below MIN_VECTOR_AREA.
    """
    try:
        drawings = page.get_drawings()
    except Exception:
        return []
    boxes: List[fitz.Rect] = []
    for d in drawings:
        rect = d.get("rect")
        if rect is None or rect.is_empty:
            continue
        boxes.append(fitz.Rect(rect))

    # Merge until stable.
    merged = _merge_rects(boxes, gap=VECTOR_CLUSTER_GAP)

    # Filter by area (use width * height — fitz.Rect.get_area not available).
    return [r for r in merged if r.width * r.height >= MIN_VECTOR_AREA]


def _merge_rects(rects: List[fitz.Rect], gap: float) -> List[fitz.Rect]:
    """Iteratively merge rects that overlap or touch within `gap` points."""
    out = [fitz.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(out):
            j = i + 1
            while j < len(out):
                if _rects_close(out[i], out[j], gap):
                    out[i] = out[i] | out[j]  # union
                    del out[j]
                    changed = True
                else:
                    j += 1
            i += 1
    return out


def _rects_close(a: fitz.Rect, b: fitz.Rect, gap: float) -> bool:
    """True if two rects overlap or are within `gap` PDF points."""
    if a.intersects(b):
        return True
    # Expand `a` by `gap` on all sides and test intersection.
    expanded = fitz.Rect(a.x0 - gap, a.y0 - gap, a.x1 + gap, a.y1 + gap)
    return expanded.intersects(b)


# Pad each region by this many PDF points before rendering so captions
# and borders don't get cropped.
REGION_PADDING = 4
# Caption must be within this many points below the region.
CAPTION_SEARCH_DISTANCE = 40
# DPI for rendered assets.
ASSET_DPI = 220


def extract_page_assets(
    page: fitz.Page,
    stem: str,
    asset_dir: Path,
    page_num: int,
) -> List[Tuple[fitz.Rect, str]]:
    """Render all figure regions on a page and return (rect, markdown) pairs.

    `stem` is the markdown output filename without extension — used to
    build an asset subdirectory name. `page_num` is the 1-indexed page
    number used in the asset filename.
    """
    raster = find_raster_regions(page)
    vector = find_vector_regions(page)

    # Combine and merge overlapping regions.
    combined = _merge_rects(raster + vector, gap=REGION_PADDING)
    if not combined:
        return []

    asset_dir = Path(asset_dir)
    asset_dir.mkdir(parents=True, exist_ok=True)

    # Harvest caption candidates from page text.
    captions = _find_caption_candidates(page)

    results: List[Tuple[fitz.Rect, str]] = []
    for idx, rect in enumerate(combined):
        caption_text = _match_caption(rect, captions)
        padded = fitz.Rect(
            max(0, rect.x0 - REGION_PADDING),
            max(0, rect.y0 - REGION_PADDING),
            min(page.rect.x1, rect.x1 + REGION_PADDING),
            min(page.rect.y1, rect.y1 + REGION_PADDING),
        )
        asset_name = f"page-{page_num:04d}-figure-{idx + 1:02d}.png"
        asset_path = asset_dir / asset_name
        try:
            pix = page.get_pixmap(dpi=ASSET_DPI, clip=padded, alpha=False)
            pix.save(str(asset_path))
        except Exception:
            continue

        rel = f"{asset_dir.name}/{asset_name}"
        alt = caption_text if caption_text else f"Figure on page {page_num}"
        md = f"![{alt}]({rel})"
        if caption_text:
            md = f"{md}\n\n*{caption_text}*"
        results.append((padded, md))
    return results


def _find_caption_candidates(page: fitz.Page) -> List[Tuple[fitz.Rect, str]]:
    """Return (bbox, text) pairs for lines on the page that match CAPTION_RE."""
    try:
        page_dict = page.get_text("dict")
    except Exception:
        return []
    out: List[Tuple[fitz.Rect, str]] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # text blocks only
            continue
        for line in block.get("lines", []):
            text = " ".join(
                span.get("text", "") for span in line.get("spans", [])
            ).strip()
            if not text:
                continue
            if CAPTION_RE.match(text):
                bbox = line.get("bbox")
                if not bbox:
                    continue
                out.append((fitz.Rect(*bbox), text))
    return out


def _match_caption(
    region: fitz.Rect,
    captions: List[Tuple[fitz.Rect, str]],
):
    """Return the closest caption within CAPTION_SEARCH_DISTANCE below region."""
    best = None
    best_dist = float("inf")
    for bbox, text in captions:
        # Caption must be below (or overlapping) the region, roughly
        # within its horizontal span.
        if bbox.y0 < region.y0:
            continue
        dy = bbox.y0 - region.y1
        if dy > CAPTION_SEARCH_DISTANCE:
            continue
        # Horizontal overlap check: caption intersects region's x-range.
        if bbox.x1 < region.x0 or bbox.x0 > region.x1:
            continue
        if dy < best_dist:
            best_dist = dy
            best = text
    return best
