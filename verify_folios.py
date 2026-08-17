#!/usr/bin/env python3
"""Verify a scanned PDF's printed page numbers by reading them off the page images.

WHY THIS EXISTS

convert.py already captures printed folios from a scan and, where it cannot read one,
INTERPOLATES it from a consensus offset. That is the right behaviour — a folio missed
because it sits under a fold or inside a figure should not leave a hole. But it means a
converted book's page numbers are part measurement and part arithmetic, and nothing
afterwards can tell you which is which, or whether the arithmetic is right.

The failure that matters is not a misread digit. It is a PAGINATION ANOMALY: an
unnumbered plate section, an inserted errata leaf, a bound-in map. Every folio after it
shifts, and because interpolation applies one constant offset across the whole book, the
output is smooth, self-consistent, and wrong from that point on. A reader sent to page 214
finds page 206.

Interpolation cannot surface that. It smooths it. So this reads the folios back off the
page images and looks for the one signature that distinguishes a real shift from OCR
noise:

    NOISE     scattered pages disagreeing, each implying its own offset
    SHIFT     the offset CHANGES at some page and HOLDS there

A single page reading 31 where the book says 81 is tesseract misreading an 8. Twenty
consecutive pages all reading exactly 8 less is a plate section.

Note the shape of that test. An earlier version asked "which offset is not the most
common one", and it inverts the moment the shifted region is larger than the correct one:
a plate section a third of the way into a book makes the GOOD pages the minority, and the
tool indicts them. A transition between two established runs has no such orientation. It
does not care which side is bigger.

WHAT IT DOES NOT DO

It knows nothing about your corpus, your frontmatter, or where you file things. It takes
a PDF and reports what its pages say. Comparing that against a converted file's own
markers is a job for whatever holds those files.

USAGE
    python verify_folios.py book.pdf
    python verify_folios.py book.pdf --json report.json
    python verify_folios.py book.pdf --pages 0-99 --dpi 400

EXIT
    0  no shift found
    1  the pagination shifts somewhere (the offset changes and stays changed)
    2  too few folios could be read to say anything — NOT a pass
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

# A folio standing alone. Four digits max, so a year printed in a running head is
# admitted here and rejected later by the offset check, rather than being silently
# reinterpreted as a page number.
_STANDALONE = re.compile(r"^\d{1,4}$")
_EDGE = re.compile(r"^(\d{1,4})\b|\b(\d{1,4})$")

# An adjacent run must reach this length before it is called an anomaly rather than
# noise. Two consecutive misreads are common (facing pages share a scan artifact);
# three consecutive pages agreeing on a NEW offset is not a coincidence.
MIN_ANOMALY_RUN = 3

# Below this, the report is "cannot say", never "clean". A check that reads nothing and
# reports no anomaly is worse than no check, because it looks like a pass.
MIN_READ_FRACTION = 0.25

# Bands to try, in order, when the first pass cannot conclude. The default 0.11 is tuned to
# a folio sitting in the outer margin; a running head set lower falls outside it and the
# tool reports "inconclusive" on a book whose folios are perfectly legible.
#
# marrow-behind-the-executive-mask is the case. Its folio sits at the END of the running
# head ("The Second Week: Emphasis on the Group  •  101"), about 13% down the page. At 0.11
# the band cut it off and only 41 of 146 folios were read; the answer was "inconclusive",
# which is honest but useless. Raising the DPI to 400 changed nothing, because resolution
# was never the problem. At 0.17 the same scan yields 126 folios and a constant offset.
#
# Widening only ever runs when the pass BEFORE it could not conclude, so it cannot turn a
# real verdict into a different one — only "cannot say" into an answer.
WIDER_BANDS = (0.17, 0.24)

# How many unread pages a single segment may span before its readings stop counting as
# evidence about each other. A shift is physical: the pages it moves are contiguous. Three
# readings agreeing at one offset on pages 10, 20 and 30 with everything between unread are
# not a run, they are three coincidences — and treating them as a run manufactures a
# transition against a perfectly good book (codex, 2026-08-17). Splitting a GENUINE segment
# by this rule is harmless: two segments at the same offset yield no transition.
MAX_SEGMENT_GAP = 5


def _ocr(png_path: str) -> str:
    """OCR one band image. Prefers pytesseract (requirements-ocr.txt), falls back to the
    tesseract binary so the tool still runs where only the CLI is installed."""
    try:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(png_path), config="--psm 6")
    except ImportError:
        pass
    try:
        out = subprocess.run(
            ["tesseract", png_path, "stdout", "--psm", "6"],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def folio_from_text(text: str) -> int | None:
    """The folio off one OCR'd margin band.

    A number ALONE on its line is the folio. Otherwise a number at the very start or end
    of a line, which is the running-head-plus-folio case ("214  The Knowing-Doing Gap").
    A number in the middle of a line is prose or a citation, and is ignored.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    for ln in lines:
        if _STANDALONE.match(ln):
            return int(ln)
    for ln in lines:
        m = _EDGE.search(ln)
        if m:
            return int(m.group(1) or m.group(2))
    return None


def read_folios(pdf: str, dpi: int = 300, band: float = 0.11,
                pages: range | None = None, progress=None) -> dict[int, int]:
    """{page index (0-based) -> folio read off that page's margin}.

    Both margins are tried because books put the folio at the head or the foot, and a
    single book does both (chapter openers drop to the foot). Pages whose margins yield
    no number are simply absent from the result.
    """
    import fitz  # PyMuPDF, a core requirement

    doc = fitz.open(pdf)
    try:
        idxs = pages if pages is not None else range(doc.page_count)
        found: dict[int, int] = {}
        for i in idxs:
            if i >= doc.page_count:
                break
            page = doc[i]
            r = page.rect
            h = band * r.height
            for clip in (
                fitz.Rect(r.x0, r.y0, r.x1, r.y0 + h),
                fitz.Rect(r.x0, r.y1 - h, r.x1, r.y1),
            ):
                pix = page.get_pixmap(dpi=dpi, clip=clip)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
                    fh.write(pix.tobytes("png"))
                    tmp = fh.name
                try:
                    got = folio_from_text(_ocr(tmp))
                finally:
                    os.unlink(tmp)
                if got is not None:
                    found[i] = got
                    break
            if progress:
                progress(i)
        return found
    finally:
        doc.close()


def segments(offsets: dict[int, int]) -> list[list[int]]:
    """The read pages, in order, grouped into maximal runs that share one offset.

    Small index gaps are allowed inside a segment — pages whose margins yielded nothing
    are simply absent, and a book does not become two books because tesseract missed page
    84. Gaps larger than MAX_SEGMENT_GAP do break the segment, because past that distance
    the readings are no longer evidence about each other.
    """
    out: list[list[int]] = []
    for i in sorted(offsets):
        same_offset = out and offsets[out[-1][-1]] == offsets[i]
        near = out and (i - out[-1][-1]) <= MAX_SEGMENT_GAP
        if same_offset and near:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def find_transitions(offsets: dict[int, int]) -> list[dict]:
    """Points where the offset CHANGES and stays changed.

    Detecting a shift by "which offset is not the most common one" is fragile: it inverts
    as soon as the shifted region is larger than the correct one, and then the anomaly is
    reported against the good pages. A plate section bound in at page 60 of a 140-page
    book does exactly that.

    A pagination shift is not a minority, it is a TRANSITION — the offset changes at some
    page and holds. So the signature is two ESTABLISHED segments (each at least
    MIN_ANOMALY_RUN pages, which noise cannot reach) meeting at different offsets. Short
    segments between them are misreads and are stepped over, not treated as boundaries.
    """
    established = [s for s in segments(offsets) if len(s) >= MIN_ANOMALY_RUN]
    out: list[dict] = []
    for prev, nxt in zip(established, established[1:]):
        a, b = offsets[prev[-1]], offsets[nxt[0]]
        if a == b:
            continue
        out.append({
            "from_offset": a,
            "to_offset": b,
            "last_page_before": prev[-1],
            "first_page_after": nxt[0],
            "shift": b - a,
            "length": len(nxt),
            "folios": [offsets[i] + i for i in nxt[:6]],
        })
    return out


def analyse(folios: dict[int, int], total_pages: int) -> dict:
    """Turn read folios into a verdict. Pure — no I/O, so it is directly testable."""
    offsets = {i: f - i for i, f in folios.items()}
    counts = Counter(offsets.values())
    dominant, dominant_n = counts.most_common(1)[0] if counts else (None, 0)

    disagreeing = sorted(i for i, o in offsets.items() if o != dominant)
    anomalies = find_transitions(offsets)
    read_fraction = len(folios) / total_pages if total_pages else 0.0
    # An offset is ESTABLISHED when adjacent pages agree on it. Without at least one, the
    # readings are noise however many there are — the failure case is OCR grabbing a
    # non-folio like "CHAPTER 4" off every page, which yields a different offset per page,
    # no segment at all, no transitions, and therefore a confident exit 0 without a single
    # real folio having been read (codex, 2026-08-17). Read fraction alone cannot see that.
    established = [s for s in segments(offsets) if len(s) >= MIN_ANOMALY_RUN]
    supported = sum(len(s) for s in established)
    return {
        "pages": total_pages,
        "folios_read": len(folios),
        "read_fraction": round(read_fraction, 4),
        "dominant_offset": dominant,
        "pages_at_dominant_offset": dominant_n,
        "disagreeing_pages": disagreeing,
        "anomalies": anomalies,
        "pages_in_established_runs": supported,
        "conclusive": read_fraction >= MIN_READ_FRACTION and bool(established),
    }


def render(result: dict) -> str:
    out = [
        f"pages {result['pages']}, folios read {result['folios_read']} "
        f"({result['read_fraction']:.1%})"
        + (f", margin band {result['band']}" if result.get("band") else ""),
    ]
    if not result["conclusive"]:
        if result["read_fraction"] < MIN_READ_FRACTION:
            out.append(
                f"  TOO FEW FOLIOS READ to draw a conclusion (floor is {MIN_READ_FRACTION:.0%}).\n"
                f"  This is not a pass. Try --dpi 400, or a wider --band, or the scan is unnumbered."
            )
        else:
            out.append(
                "  NO STABLE OFFSET. Folios were read, but no run of adjacent pages agrees on\n"
                "  one offset — the signature of OCR lifting a non-folio (a chapter number, a\n"
                "  figure label) out of the margin band. This is not a pass. Wider bands were\n"
                "  already tried; the folio may sit inside the text block, or there may be none."
            )
        return "\n".join(out)
    out.append(
        f"  dominant offset {result['dominant_offset']:+d} "
        f"on {result['pages_at_dominant_offset']} pages"
    )
    out.append(f"  pages disagreeing: {len(result['disagreeing_pages'])}")
    if not result["anomalies"]:
        out.append(
            "  NO PAGINATION ANOMALY. Every disagreement is isolated, which is the OCR-noise\n"
            "  signature; a real shift moves a run of adjacent pages together."
        )
    else:
        out.append(f"  {len(result['anomalies'])} PAGINATION SHIFT(S) — the offset changes and stays changed:")
        for a in result["anomalies"]:
            out.append(
                f"      between page {a['last_page_before']} and page {a['first_page_after']}: "
                f"offset {a['from_offset']:+d} -> {a['to_offset']:+d} "
                f"(a shift of {a['shift']:+d}), holding for {a['length']} read pages"
            )
        out.append(
            "  Interpolated folios past the first shift are suspect. A reader sent to a page\n"
            "  beyond it lands somewhere else."
        )
    return "\n".join(out)


def _parse_pages(spec: str) -> range:
    m = re.fullmatch(r"(\d+)-(\d+)", spec)
    if not m:
        raise argparse.ArgumentTypeError("--pages wants a range like 0-99")
    return range(int(m.group(1)), int(m.group(2)) + 1)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read a scanned PDF's printed page numbers off the page images and "
                    "report whether its pagination is coherent.",
    )
    ap.add_argument("pdf")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--band", type=float, default=0.11,
                    help="fraction of page height treated as the margin band (default 0.11)")
    ap.add_argument("--pages", type=_parse_pages, default=None, help="e.g. 0-99")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--no-widen", action="store_true",
                    help="do not retry at a wider margin band when the result is inconclusive")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        print(f"verify_folios: no such file: {args.pdf}", file=sys.stderr)
        return 2

    import fitz

    doc = fitz.open(args.pdf)
    total = doc.page_count
    doc.close()

    def progress(i):
        if not args.quiet and i % 25 == 0:
            print(f"  ... page {i}", file=sys.stderr, flush=True)

    # Intersect the requested range with the document, or a range running past EOF makes
    # the denominator too large and turns a good read into a spurious "inconclusive".
    scanned = len([i for i in args.pages if i < total]) if args.pages else total

    # Widen the band and retry when a pass cannot conclude. See WIDER_BANDS: the common
    # cause of "inconclusive" is a running head set lower than the default band, not
    # anything wrong with the book, and raising the DPI does not touch it.
    bands = [args.band] + ([] if args.no_widen else [b for b in WIDER_BANDS if b > args.band])
    folios: dict[int, int] = {}
    result: dict = {}
    for attempt, band in enumerate(bands):
        if attempt and not args.quiet:
            print(f"  inconclusive at band {bands[attempt - 1]}; retrying at band {band}",
                  file=sys.stderr, flush=True)
        folios = read_folios(args.pdf, dpi=args.dpi, band=band,
                             pages=args.pages, progress=progress)
        result = analyse(folios, scanned)
        result["band"] = band
        # Only an inconclusive pass is retried, so widening can never turn one verdict
        # into a different one — only "cannot say" into an answer.
        if result["conclusive"]:
            break
    result["pdf"] = os.path.basename(args.pdf)
    result["folios"] = {str(k): v for k, v in sorted(folios.items())}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    if not args.quiet:
        print(render(result))

    if not result["conclusive"]:
        return 2
    return 1 if result["anomalies"] else 0


if __name__ == "__main__":
    sys.exit(main())
