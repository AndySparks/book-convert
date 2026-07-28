# The asset invariant

> **The output never contains a reference to a file that does not exist.**

Closes [issue #34](https://github.com/AndySparks/BookConvert/issues/34).

## What went wrong

A conversion could emit `![](_page_64_Figure_7.jpeg)` into the markdown while
writing no such file. Measured in the consuming vault on 2026-07-28:

| | |
|---|---|
| Sources carrying local figure references | 53 |
| Of those, sources with **dangling** references | **49** |
| Total dangling references | **1,140** |

~92% of every converted source that should show a figure showed none — with
`quality_score: 1.0` and `extracted_assets: 0` in the sidecar, reporting the
truth to nobody.

## The mechanism

Two bugs in the marker backend's asset harvesting, either of which alone was
enough:

1. **The suffix.** Marker writes its figures as `.jpeg`. The harvesting code
   globbed `rglob("*.png")` and `rglob("*.jpg")` out of marker's scratch
   directory. `fnmatch("_page_64_Figure_7.jpeg", "*.jpg")` is `False`, so the
   files were never found — and the scratch directory was a
   `TemporaryDirectory`, so they were deleted moments later.
2. **The slash.** The reference-rewriting regex was
   `!\[([^\]]*)\]\((?:[^)]*/)([^)]+)\)` — the `(?:[^)]*/)` group is not
   optional, so it only matches a target containing a directory separator.
   Marker's references are bare filenames. Even on the path where the files
   *were* found, the references would not have been repointed.

Both are the kind of bug that a test asserting "images get moved" passes over,
because the code path is only reached when the glob matches. What catches them
is asserting the *property* — zero dangling references in the emitted markdown
— which is what `tests/test_asset_invariant.py` does.

## Why extraction is now the default

The issue proposed two routes. Both are implemented, at different layers.

**Route 1 — extraction becomes the default (`--extract-images` defaults on).**
This is the primary fix. The decisive fact is that the figures are already
extracted internally: marker finds them whether or not we ask, and pymupdf's
detector runs against pages we have already opened. The old default paid the
full cost of finding a figure and then threw the file away, which is pure
loss. `--no-extract-images` is the opt-out for a caller who genuinely wants
text only.

The deeper reason is the one the issue names: *the instinct is to document the
flag harder, and that is treating the symptom*. The consuming runbook never
mentioned `--extract-images` — not once — so every ingest that followed the
documented process produced broken output. A default that requires knowing a
flag exists in order to avoid producing broken output is a bad default, and no
amount of documentation fixes it.

**Route 2 — refuse to emit a reference to an asset we did not write.** This is
the backstop, and it runs unconditionally on every backend at the end of every
conversion (`convert._finalize_assets` → `assets.enforce_reference_invariant`).
Route 1 makes the invariant cheap to satisfy; route 2 is what makes it *true*
— including when extraction is disabled, when a backend loses its assets, and
when a future backend emits a reference to something it never wrote.

A stripped reference leaves an HTML comment:

```markdown
<!-- bookconvert: image omitted, asset not extracted: _page_64_Figure_7.jpeg -->
```

It renders as nothing, and it means a thin conversion is diagnosable by a human
reading the file rather than silent. The sidecar counts them in
`dangling_refs_stripped`, and a non-zero count adds a warning.

## Backend coverage

| Backend | Emits references? | Route |
|---|---|---|
| **marker** | Yes — bare `_page_N_Figure_M.jpeg`. **This is the one that broke.** | Assets harvested by suffix set (not two globs) and references repointed by basename (not by a regex needing a `/`). `--no-extract-images` forwards `--disable_image_extraction` to `marker_single`. |
| **pymupdf** | Only when it has just written the file | Extraction default flipped on. Structurally cannot dangle: the reference is stitched in by the same code that saves the PNG. |
| **pymupdf4llm** | Yes, into `<stem>_images/` | `write_images` now follows `extract_images` instead of being hardcoded on. Its path-prefix rewrite was already correct; the sweep covers what it misses. |
| **docling** | No — its default export mode emits `<!-- image -->` placeholders | Swept anyway. The invariant is a property of BookConvert's output, not a favour done to the backends we happen to distrust. |
| **ocr** (tesseract) | No — plain text only | Swept anyway. |
| **pandoc** (EPUB) | **Yes** — the epub's internal media paths, for images it never writes | Route 2 only, deliberately. Extraction is not the answer here: the images an epub carries that survive `_clean_pandoc_output`'s decorative-glyph filter are overwhelmingly publisher furniture (covers, ornaments, imprint marks), and the epub path is documented as text-only. The references are stripped. |

So marker is the backend that motivated the issue, but it was not the only one
that could dangle — pandoc dangles by construction on any epub whose image
references carry alt text.

## The asset manifest

The second half of the issue. Consumers were relocating assets by
pattern-matching `_page_N_Figure_M.jpeg` — marker's internal naming convention,
an implementation detail crossing a module boundary. A rename inside marker
silently breaks every downstream filer.

The sidecar now carries an explicit manifest:

```json
"assets": [
  {
    "path": "MyBook_images/_page_64_Figure_7.jpeg",
    "bytes": 48213,
    "references": [
      {"target": "MyBook_images/_page_64_Figure_7.jpeg", "alt": "", "line": 812}
    ]
  }
],
"extracted_assets": 1,
"dangling_refs_stripped": 0
```

- **`path`** — the asset, relative to the markdown file. Move this.
- **`bytes`** — size on disk, for a consumer that wants to skip 200-byte
  ornaments.
- **`references`** — every place in the markdown that points at this asset.
  `target` is the link target *exactly as written*, so rewriting is a
  substitution of `](target)`; `line` is 1-indexed and accurate against the
  file as shipped (the manifest is recomputed after the cleanup pass, which
  rewrites the markdown underneath it). `alt` is the alt text.

An asset that nothing references still gets an entry with `references: []` —
that is information, being the signature of a reference lost upstream.

The full round trip is exercised by
`test_manifest_round_trip_relocates_every_asset`: a consumer relocates every
asset and rewrites every reference without looking at a filename, a suffix, or
a page-number pattern.

## Verifying the invariant

```python
import assets
assets.count_dangling_refs("output/MyBook.md")   # 0, always
```

```bash
jq '.dangling_refs_stripped, (.assets | length)' output/*.report.json
```
