# BookConvert

Convert PDF and EPUB books to clean Markdown files for use in [Claude Projects](https://claude.ai), NotebookLM, and other LLM tools.

Conversion paths:
- **PyMuPDF** (PDF default): Fast, reliable text extraction that works on any Python 3.7+
- **pymupdf4llm** (PDF): Text + image extraction, optimized for LLM ingestion (requires Python 3.10+)
- **Marker** (PDF): High-quality markdown conversion (requires Python 3.10+)
- **Docling** (PDF): IBM's layout-aware pipeline (requires Python 3.10+)
- **OCR** (PDF): Tesseract OCR for scanned/image-based PDFs
- **Pandoc** (EPUB): Preserves the epub's chapter structure as markdown headings

## Setup

### Default install (text-only extraction)

```bash
git clone https://github.com/AndySparks/book-convert.git
cd book-convert
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs PyMuPDF plus `pyspellchecker` (a small pure-Python dictionary
used by the default-on cleanup pass) and gives you the default
text-extraction backend. Works on Python 3.7+.

### Optional backends (install into .venv-marker)

Higher-quality backends (`pymupdf4llm`, `marker-pdf`, `docling`) require
Python 3.10+. Install them into a separate `.venv-marker` so your default
venv stays small:

```bash
python3.12 -m venv .venv-marker
.venv-marker/bin/pip install -r requirements-marker.txt        # marker-pdf
.venv-marker/bin/pip install -r requirements-pymupdf4llm.txt   # pymupdf4llm
.venv-marker/bin/pip install -r requirements-docling.txt       # docling
```

### OCR backend

```bash
brew install tesseract poppler
pip install -r requirements-ocr.txt
```

### EPUB support

```bash
brew install pandoc
```

EPUB files route through pandoc regardless of `--method` selection.

## Usage

### Convert a single PDF or EPUB

```bash
python convert.py input/MyBook.pdf
python convert.py input/MyBook.epub    # EPUB -> markdown via pandoc
```

### Convert all PDFs and EPUBs in a directory

```bash
python convert.py input/
```

Directory mode picks up both `.pdf` and `.epub` files. The tool dispatches each one to the right toolchain automatically.

### Choose a conversion method

```bash
python convert.py input/MyBook.pdf --method pymupdf          # default, fast, text-only
python convert.py input/MyBook.pdf --method pymupdf4llm      # text + images, needs Py3.10+
python convert.py input/MyBook.pdf --method marker           # highest quality, slowest
python convert.py input/MyBook.pdf --method docling          # IBM's layout-aware pipeline
python convert.py input/ScannedBook.pdf --method ocr         # tesseract OCR
```

### Figures and images

Extraction is **on by default**. Figures, diagrams, and embedded raster
images are written to a sibling directory (`output/<stem>_assets/` for
pymupdf, `output/<stem>_images/` for marker and pymupdf4llm), and the
markdown carries image references to them at the right page position.

```bash
python convert.py input/MyBook.pdf                      # figures kept
python convert.py input/MyBook.pdf --no-extract-images  # text only
```

**The invariant: the output never contains a reference to a file that does
not exist.** With `--no-extract-images` the references to the skipped
figures are *stripped*, not left dangling — a text-only conversion is
complete, never perforated. Each stripped reference leaves an HTML comment
(`<!-- bookconvert: image omitted, asset not extracted: ... -->`) so a thin
conversion is diagnosable rather than silent, and the sidecar records
`dangling_refs_stripped`.

This is why extraction became the default. The old default found the
figures, emitted references to them, and then threw the files away; a
caller had to know a flag existed to avoid producing broken output. See
`docs/asset-invariant.md`.

### The asset manifest

The sidecar carries an `assets` array — one entry per file the conversion
wrote, with the references pointing at it:

```json
"assets": [
  {
    "path": "MyBook_images/_page_64_Figure_7.jpeg",
    "bytes": 48213,
    "references": [
      {"target": "MyBook_images/_page_64_Figure_7.jpeg", "alt": "", "line": 812}
    ]
  }
]
```

`path` is relative to the markdown file. A consumer relocating a conversion
moves each `path` and rewrites each `references[].target` where it appears
in a `](...)` — knowing nothing about how any backend names its files.
Do not pattern-match `_page_N_Figure_M.jpeg`: that is marker's private
convention and it can change without notice.

```bash
jq '.assets[] | .path, (.references | length)' output/MyBook.report.json
```

### Page locators

Every locator-emitting backend writes one comment per page:

    <!-- page_pdf=59 page_printed=47 -->
    <!-- page_pdf=3 page_printed=none -->

`page_pdf` is the 1-based index of the page inside the PDF file. It is
always accurate, and is sparse — pages with no extractable text are
omitted.

`page_printed` is the page number **printed on the page**. It is the only
address valid for scholarly citation. It is `none` when the source carries
no printed page number, which is normal for ebook-derived PDFs and
universal for EPUB.

Never present a `page_pdf` value as a page number. The sidecar declares
which you have:

| `page_numbering` | Meaning | Backends |
|---|---|---|
| `printed` | Real page numbers were captured | `pymupdf` and `marker`, when printed page numbers were actually found |
| `pdf_only` | PDF page index only | `pymupdf` / `marker` (no printed numbers found), `pymupdf4llm`, `ocr` |
| `none` | No locators emitted at all | `pandoc` (EPUB — reflowable, no pages exist), `docling` |

`pymupdf` and `marker` both decide between `printed` and `pdf_only` at runtime;
the others have a fixed capability. Read `page_numbering` from the sidecar
rather than assuming it from the `--method` you asked for.

Where printed-page-number survival is sparse, `page_printed_offset` is
derived from the captured samples and used to fill the gaps — but only
when at least 3 arabic samples reach a consensus
(`page_printed_offset_consistent: true`), and only for PDF pages that fall
between the first and last captured sample. A book that renumbers partway
through, or that has printed page numbers only in part of the text, gets no
interpolation (or interpolation clamped to that span) rather than invented
page numbers — and interpolation never produces a printed page number
below 1.

Consensus is not unanimity. At least 85% of the arabic samples must agree
on one offset, and the samples that disagree must be scattered — two
dissenters within 2 sheets of each other are read as a renumbering or a
page-order defect and refuse the whole book. Below 8 samples, unanimity is
still required, because at that size a misread digit and a genuine second
numbering sequence are indistinguishable. A folio that contradicts an
adopted consensus is treated as an OCR misread: it is suppressed, replaced
by the interpolated value, and reported in `warnings` rather than published
as a page number a reader would trust. Every refusal is likewise reported
in `warnings` with its reason, so low coverage always comes with an
account of itself.

A folio does not have to stand alone on its line to be read. Many editions
set it on the same line as the running head, pinned to the outer edge of the
spread — `52 THE TAO OF COACHING` on a verso, `MOTIVATING 67` on a recto. A
numeral is lifted out of such a line only when it is the first or last token
on it, when what remains is a running head already seen on three or more
pages, and when the line as a whole does *not* repeat — a folio changes
every page, so a band line that repeats verbatim has a constant number in it
(a year in the title, a part or chapter number) and that number belongs to
the title, not to the pagination. Roman numerals are never lifted out of a
shared line. A folio standing alone always wins over one sharing a line.

Check coverage after any conversion:

    jq '.page_numbering, .page_printed_coverage, .page_printed_offset_consistent' output/<Title>.report.json

### Post-conversion cleanup (on by default)

Every conversion runs a verbatim-safe cleanup pass over the emitted
markdown that repairs the extraction artifacts no backend fixes on its own:

- **Dropped-space joins** where a function word is glued to its neighbour
  (`thefrozen` → `the frozen`, `sucha` → `such a`). The joined form is never
  a real English word, so splitting *restores* the author's text.
- **Stray-consonant citation ghosts** (`—wWilliam Golding` → `—William Golding`).
- **Picture-text blocks**: a real Table of Contents rendered as a table is
  unwrapped and kept; OCR garble (ISBN barcodes, etc.) is dropped.

The pass is designed never to mangle a real word: it only splits at a
whitelisted function-word boundary, so British spellings (`colour`),
coinages (`givenness`), proper nouns, and quoted literary coinages
(Joyce's `moocow`) pass through untouched. What it changed is recorded in
the sidecar report under `cleanup`.

```bash
python convert.py input/MyBook.pdf              # cleanup runs automatically
python convert.py input/MyBook.pdf --no-clean   # skip it
```

The de-join step uses `pyspellchecker` (installed by `requirements.txt`). If
it is ever missing, cleanup degrades gracefully — the dictionary-free repairs
still run and a warning is recorded.

### Passing flags through to marker

The marker backend accepts extra flags via `--marker-args`, forwarded
verbatim to `marker_single`:

```bash
python convert.py input/MyBook.pdf --method marker --marker-args '--use_llm'
python convert.py input/MyBook.pdf --method marker --marker-args '--html_tables_in_markdown'
```

The two that matter for table-heavy books:

- `--use_llm` activates marker's LLM table processors, which fix merged
  headers and rows split across lines. It needs an LLM service
  configured (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or a local ollama
  endpoint) — see `marker_single --help` for `--llm_service`.
- `--html_tables_in_markdown` emits `<table>` with real `colspan` /
  `rowspan`. GFM markdown cannot express spanning header cells at all,
  so this is the only way to preserve a multi-level table header —
  at the cost of much less readable output.

Run `marker_single --help` for the full flag list.

### Sidecar conversion report

Every conversion writes a `<stem>.report.json` alongside the markdown
containing: method used, page count, OCR pages, extracted assets, the
asset manifest, `dangling_refs_stripped`, quality score,
`cleaned`/`cleanup` stats, table counts, and any warnings.
Useful for inspecting a batch run:

```bash
jq '.method,.extracted_assets,.quality_score' output/*.report.json
```

**Table fidelity.** `table_captions_seen` counts `TABLE 9-1` style
captions in the output; `tables_emitted` counts the grids actually
produced. A wide gap means the captions survived but their grids
collapsed into prose — the failure a three-page spot-check will miss.
The report adds an explicit warning when captions outnumber grids.

```bash
jq '.tables_emitted, .table_captions_seen, .warnings' output/*.report.json
```

Note that the `ocr` (tesseract) backend has **no** table reconstruction
at all, so it reports `0` emitted against however many captions it read.
For a book with real tables, use `marker`.

**Heading fidelity (EPUB).** `headings_emitted` counts markdown headings in
the converted body — BookConvert's own title line is excluded, so `0` means
`0`. `heading_source` says where they came from:

| `heading_source` | Meaning |
|---|---|
| `semantic` | The epub carried real `<h1>`–`<h6>` tags. The normal case. |
| `nav` | The epub had none; headings were derived from `toc.ncx` / the EPUB 3 nav document. Authoritative and ordered. |
| `class-heuristic` | No headings *and* no usable nav; derived from chapter-ish CSS classes (`<p class="chaphead">`). Lower confidence — spot-check it. |
| `none` | No signal at all. The output has no structural addressing whatsoever. |

Both fields are `null` on the PDF backends, which do not measure them.
`null` means "not measured", which is a different claim from `0`.

```bash
jq '.heading_source, .headings_emitted' output/*.report.json
```

This matters more for EPUB than for PDF: an epub is reflowable, so
`page_numbering` is always `none` and headings are the *only* address the
file has. `heading_source: "none"` on an epub means you have a text blob.

### Archive source PDFs after conversion

```bash
python convert.py input/ --archive                    # Move converted books into archive/
python convert.py input/ --archive --archive-dir old/ # Custom archive location
```

Failed conversions and `--skip-existing` skips are left in `input/`. Name collisions in the archive are preserved by appending a timestamp to the new copy. Both PDFs and EPUBs archive through the same flag.

### Skip already-converted files

```bash
python convert.py input/ --skip-existing
```

### Specify output directory

```bash
python convert.py input/MyBook.pdf --output output/Philosophy/
```

## How it works

1. Drop your PDF(s) or EPUB(s) into the `input/` folder
2. Run `convert.py` -- PDFs go through **PyMuPDF** by default, EPUBs go through **pandoc**
3. For text + image extraction, use `--method pymupdf4llm` (requires Python 3.10+)
4. For higher-quality PDF formatting, use `--method marker` or `--papers` (requires Python 3.10+)
5. For IBM's layout-aware pipeline, use `--method docling` (requires Python 3.10+)
6. For scanned books (where the pages are images), use `--method ocr` or `--ocr`
7. Converted markdown appears in `output/`, with a `<stem>.report.json` sidecar alongside each file

### EPUB conversion

EPUBs go through pandoc with raw HTML disabled, which gives you clean chapter headings, preserved emphasis, and usable footnote anchors without the publisher layout scaffolding leaking into the output. The `--method` flag is PDF-only; EPUBs always use pandoc. Install with `brew install pandoc`.

**Headings when the epub has none.** Pandoc can only map headings the source
actually carries, and plenty of trade epubs style their chapter openers as
`<p class="chaphead">` rather than `<h1>`. Those books used to convert to a
single flat document with no warning — and because an epub is reflowable,
that leaves the file with no addressing of any kind. BookConvert now checks
for semantic `h1`–`h6` first and, finding none, derives headings from the
epub's own navigation (`toc.ncx` for EPUB 2, the nav document for EPUB 3),
mapping nav nesting to heading depth. A chapter-ish CSS-class heuristic is
the fallback to the fallback. The source file is never modified; a rewritten
copy is handed to pandoc from a temp directory. Whatever happened is
declared in the sidecar as `heading_source` + `headings_emitted` — see
[Sidecar conversion report](#sidecar-conversion-report). Implementation:
`epub_structure.py`.

### Academic papers

The PyMuPDF pipeline detects two-column layouts and reconstructs the reading order so journal articles don't come out with left and right columns interleaved. This works on clean two-column pages, merged-block pages where PyMuPDF returns both columns as one giant block, and body-plus-sidebar pages with an inset author bio. See `docs/paper-extraction-research.md` and `docs/paper-extraction-decision.md` for the detection approach and the trade-offs vs. marker-pdf.

When `convert.py` sees a document that looks like a short, mostly-two-column paper, it prints a one-line hint suggesting `--papers` for higher-quality output (on Python 3.10+).

## Using with Claude Code

This project includes a `CLAUDE.md` file, so [Claude Code](https://docs.anthropic.com/en/docs/claude-code) understands the project and can help you convert and clean up books. Just open the project directory in Claude Code and ask it to help convert your PDFs.

## Running tests

The repo has a small pytest suite under `tests/`. To run it:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # first time only
python -m pytest tests/ -v
```

The tests cover the text quality scorer that gates the pymupdf → OCR
auto-fallback. See `docs/quality-fallback-design.md` for the design
behind that feature.

## Tips

- **Start with the default mode** (PyMuPDF). It's fast and works on any Python version.
- **Use `--method pymupdf4llm`** if you have Python 3.10+ and want text plus extracted images in the markdown.
- **Use `--method marker`** if you have Python 3.10+ and want the highest-quality markdown formatting.
- **Use `--method docling`** if you have Python 3.10+ and need IBM's layout-aware pipeline for complex layouts.
- **Figures come out by default.** Pass `--no-extract-images` for text-only output; the references to the skipped figures are stripped so the markdown never points at a file that isn't there.
- **Use `--auto-ocr`** to have the tool automatically retry with OCR when pymupdf fails. This catches both fully-scanned PDFs and PDFs with non-standard font encodings that produce garbled text (e.g. ligature artifacts like `n1ethod` for `method`). Without `--auto-ocr` you'll get an error message suggesting `--method ocr` and can re-run manually.
- **OCR output may need cleanup.** Claude Code can help you fix OCR artifacts, add proper headings, and improve formatting.
- **Inspect the sidecar report** (`output/<stem>.report.json`) after each conversion to check quality score, OCR page count, and any warnings.
- **Organize your output** into subdirectories by topic (e.g., `output/Coaching/`, `output/Writing/`) to keep things tidy.
- **Use `--skip-existing`** when re-running on a directory to avoid re-converting files you already have.

## Operating notes

Things that bite in practice. None of them are bugs; all of them cost time before they were written down.

### On Apple Silicon, force marker onto the CPU

marker's surya models crash partway through a large book on the Mac GPU (`torch.AcceleratorError: index ... out of bounds`, typically around the halfway mark). The CPU path is slower but stable:

```bash
export TORCH_DEVICE=cpu PYTORCH_ENABLE_MPS_FALLBACK=1
```

`convert.py` calls `marker_single` by bare name, so the marker venv's `bin` must also be on `PATH` — invoking `.venv-marker/bin/python` alone is not enough:

```bash
export PATH="$PWD/.venv-marker/bin:$PATH"
```

If marker still misbehaves, fall back to `--method ocr` (tesseract, no GPU at all).

### Check free memory before a long conversion

marker holds roughly 8.6 GB of model weights resident. On a machine without room for them the run **does not fail — it crawls**, because the weights page in and out of swap. Observed: a book that converts in 11 minutes with headroom managed 3% of text recognition in 39 minutes when free memory had fallen to ~94 MB. That is a ~50× slowdown whose only symptom is a progress bar quietly revising its estimate upward.

`convert.py` warns when headroom is short, but the cheap habit is to close browsers and Electron apps first:

```bash
vm_stat | grep -E "Pages free|Pages inactive"   # want >8 GB across the two
```

### The checkout is shared

Several sessions may use one working tree. `convert.py` reports conversions already in flight before starting anything slow, and concurrent runs are fine — but two habits keep them out of each other's way:

- **Pass the source path directly and name the output.** `input/` is a convention, not a requirement. `convert.py /path/to/book.pdf --output output/Topic` shares nothing.
- **Never run directory mode** (`convert.py input/`) on a shared checkout. It will pick up whatever another session left in `input/`, convert it, and — with `--archive` — move it.

### A backgrounded marker run looks like a hung one

marker writes to a temp directory and only copies the finished `.md` into `output/` at the very end, so an empty output folder mid-run is normal. Launch long runs in the background and watch the log:

```bash
nohup python convert.py "$SRC" --method marker --output output/Topic --skip-check --verbose \
  > logs/my-book.log 2>&1 &
```

Note that `ps aux | grep marker_single` returns **nothing** even while marker is running, because the process command is the resolved Python interpreter path. Check the wrapper PID or look for a Python process burning several hundred percent CPU.

## Known limitations

### Folio capture is still partial when the page number sits beside a running head

A folio sharing its line with a running head is now read (see *Page numbers* above), but only where the head beside it recurs on at least three pages. That bar is what keeps a line of prose from being mistaken for pagination, and it is paid for on short chapters: a book whose recto head is the *chapter* title, running two or three pages before the next chapter starts, loses those rectos. On Landsberg's *The Tao of Coaching* the versos all carry the book title and are read; the rectos carry chapter titles and roughly half fall under the bar. Capture on that scan goes from 19 of 136 to about 52 — enough to rest the offset on the whole body instead of on nine chapter openers, not enough to call the problem closed. Tracked in [#31](https://github.com/AndySparks/book-convert/issues/31).

Two consequences worth knowing when you read a sidecar:

- Low `page_printed_coverage` on a clean scan usually means this, not a source without printed page numbers. What matters more than the coverage figure is `page_printed_offset_consistent`: with a consistent offset, the uncaptured pages are interpolated and get the same number they would have had.
- **Folio position varies by edition, not just by page.** Some books run the number at the foot of every page; others at the top outer corner. There is no safe default — render both margin bands and look before concluding a source has no page numbers.

### EPUB has no pages

EPUB is reflowable, so `page_numbering` is always `none` and there are no locators of any kind. Cite by chapter. If you need `p. N` from a work you only have as an EPUB, you need a print-faithful PDF; reconverting the EPUB will never produce one.

### Table extraction on design-heavy books

Marker's OCR of table *cells* is strong, but two things break independently of cell accuracy. Multi-level spanning headers cannot be expressed in GFM markdown at all (there is no colspan), and layout boxes or conceptual diagrams in designed books get forced into table grids, arriving visibly garbled — split words across cells, stray `<br>`, empty rows.

Check `tables_emitted` against `table_captions_seen` in the sidecar. A wide gap means captions survived but their grids collapsed. `--html_tables_in_markdown` preserves structure GFM cannot, at the cost of readability.

The failure class that actually justifies a repair pass is **silently wrong numeric cells** in statistical tables — dropped minus signs, dropped leading decimals, misaligned rows. Visible garble in a word-based matrix is annoying; a sign-flipped coefficient is a citation you cannot trust. Spot-check page images against the markdown for any book you intend to cite numerically.

## Project structure

```
book-convert/
  input/                         <- Drop your PDFs here
  output/                        <- Converted markdown files appear here
  archive/                       <- Optional: --archive moves converted source PDFs here
  logs/                          <- Conversion logs (useful for backgrounded marker runs)
  docs/                          <- Design notes (paper extraction research, decisions, results)
  tests/                         <- pytest suite
  convert.py                     <- Main conversion script
  epub_structure.py              <- EPUB nav parsing + heading derivation
  cleanup.py                     <- Post-conversion text cleanup
  assets.py                      <- Figure and image extraction
  report.py                      <- Sidecar conversion report
  requirements.txt               <- Default install (PyMuPDF only, Python 3.7+)
  requirements-marker.txt        <- marker-pdf extras (Python 3.10+)
  requirements-pymupdf4llm.txt   <- pymupdf4llm extras (Python 3.10+)
  requirements-docling.txt       <- docling extras (Python 3.10+)
  requirements-ocr.txt           <- OCR extras (tesseract + poppler required)
  requirements-dev.txt           <- Test dependencies
  CLAUDE.md                      <- Instructions for Claude Code
```

## License

MIT
