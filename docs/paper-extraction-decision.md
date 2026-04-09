# Paper Extraction: Decision

**TL;DR:** Primary path is Approach B (deep column-extraction fix in the PyMuPDF pipeline, on by default). Approach C (route academic papers to marker-pdf) becomes an opt-in `--papers` flag for users running Python 3.10+. Auto-detection is added but only used to *warn*, not to switch engines silently.

## Why not marker-pdf by default

1. **Runtime incompatible.** The default venv is Python 3.9 and marker-pdf requires 3.10+:
   ```
   marker_single --help
   TypeError: unsupported operand type(s) for |: '_GenericAlias' and 'NoneType'
   ```
   Making marker the default would break the tool for the current user on day one.

2. **Heavy dependencies.** Marker pulls ~2 GB of PyTorch + transformers + Surya weights. First run on a cold machine is an 8-10 minute download and several hundred MB of model cache. That's a bad default for a CLI that should "just work".

3. **Slow CPU throughput.** ~30–60 s per page on a laptop. A 43-paper corpus averaging 15 pages each would take 5–10 hours to reconvert. The current PyMuPDF path does the whole corpus in under 30 seconds.

4. **We don't need the ceiling.** The enhanced column detection in `convert.py` (committed as `028fc79`) already handles 43/43 of the corpus. Marker would give incremental gains on edge cases (equations, figure captions, tables) but the corpus is almost entirely running prose — those edge cases barely exist.

## Why not auto-detect and route

Auto-detection is a trap here. It creates three failure modes:
- **False-negative paper** gets treated as a book → misses the (hypothetical) quality gain.
- **False-positive book** gets treated as a paper → 10-hour marker run on a 276-page book the user only wanted quickly.
- **Silent routing** means the user can't predict which backend they'll get; they have to read the logs to know what ran.

Instead, the user explicitly opts into marker with `--papers` or `--method marker`. If they omit the flag, they get PyMuPDF every time. Predictable beats clever.

## What Approach B actually does

The current `convert.py` on `main` (commit `028fc79`) contains:

1. **`_detect_two_column_split(page)`** — word-level gutter detector. Groups words into rows with a 3pt y-tolerance, scans x near the page midpoint, finds the x with the highest "no word crosses" coverage. Requires ≥ 75% coverage AND both sides to contribute ≥ 10% of rows, so narrow single-column pages don't false-positive as two-column.

2. **`_extract_page_text(page)`** — handles three kinds of blocks on a detected 2-col page:
   - *Pure-left / pure-right* blocks → pushed to the left or right column buffer in y-order.
   - *Short crossing* blocks (title, section heading, footnote) → treated as full-width, placed as headers/inline/footers based on y relative to column content.
   - *Tall crossing* blocks (PyMuPDF merged both columns into one) → words inside the block are split at the gutter x into left / right buckets, each bucket becomes its own column contribution.

3. **Reading order** — full-width headers, then all left column top-to-bottom, then inline full-width elements, then all right column top-to-bottom, then full-width footers. This matches what the old code did for clean two-column pages and extends it to merged-block pages.

## What Approach C adds on top

1. **`--papers` CLI flag** that sets `--method marker` when present.
2. **Python version guard** in `check_dependencies` — when method is marker, verify `sys.version_info >= (3, 10)` and fail with a clear "requires Python 3.10+; use the default pymupdf method or create a 3.12 venv" error.
3. **Passive detection** of paper-like documents (≥ 50% of first 6 pages detect as 2-column, OR page count ≤ 60 AND producer metadata matches a known publisher). When detected AND `--papers` was NOT passed, print a one-line note: `Note: this looks like an academic paper. For higher-quality output, re-run with --papers (requires Python 3.10+).` This keeps routing explicit but helps users discover the marker path.

## Known issues and how each is addressed

| Known issue | Addressed by |
|---|---|
| 1. JSTOR-style fake TOCs | Already fixed in `_is_useful_toc` + `_format_embedded_toc` before this session. Will verify on re-run. |
| 2. Two-column interleaving on "clean" pages | Approach B: `_extract_page_text` already does per-column sorting with the new word-level detection. Verified on argyris1976, argyris1959, argyris1993. |
| 3. Merged-block two-column pages | Approach B: word-level split of tall crossing blocks. Verified on argyris1977, argyris1955, argyris1980_2, argyris1989, fulmer1998. |

## Rejected alternatives (see research.md for detail)

- **Nougat**: trained only on arXiv STEM; hallucinates on 1950s JSTOR scans.
- **GROBID / CERMINE / science-parse**: Java-only, integration cost too high for a Python CLI.
- **pdffigures2**: figures only, not body text.
- **Adobe PDF Extract API**: commercial, network-dependent, vendor lock-in.
- **unstructured.io hi_res**: requires detectron2 + CUDA; the fast mode has no column awareness so it doesn't help.
- **pdfplumber**: same primitives as PyMuPDF but slower, no reason to migrate.

## Open questions for the next iteration

- Should the histogram-based gutter detector replace the point-sampling version? (Listed in research.md as a clear improvement.) Defer — current version works on all 43 papers, optimization not urgent.
- Should we add font-size-based header promotion? Would fix a few minor mis-classifications. Defer until we see a real failure.
- Should the `--papers` flag force `--method marker`, or is there a way to get marker's layout quality without marker's weight? There isn't — lightweight options don't exist today. Just do the flag.
