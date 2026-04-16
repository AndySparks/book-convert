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
