# Paper Extraction Research

Survey of tools that handle academic-paper PDF → text conversion, focused on how each tool tackles the column-layout problem and what BookConvert could borrow.

**Our constraints:**
- Default venv is Python 3.9 (marker-pdf and several modern tools require 3.10+).
- No GPU assumed.
- No external runtimes (Java, Docker) in the default path.
- Output target is clean Markdown for LLM ingestion — we care about reading order and paragraph integrity more than figure / table extraction.
- Corpus is 43 Argyris papers in `input/`, mostly two-column scans and JSTOR exports from the 1950s-2000s.

---

## marker-pdf (already installed, broken in our venv)

**Approach.** Uses the Surya layout model (transformer-based object detection trained on publaynet + doclaynet) to classify each region of each page as Title / Section Header / Text / List / Table / Figure / Caption / Equation / Page Header / Page Footer. Reading order is solved per-region by another Surya model. OCR fills in glyphs when embedded text is missing or suspicious. Tables go through Surya's table recognizer; equations through a LaTeX predictor.

**Strengths.**
- Column layout is "free" — the layout model doesn't care about columns, it predicts bounding boxes and Surya's reading-order model sorts them correctly.
- Handles rotated text, footnotes, marginalia, and inset figures without special casing.
- Output is semantically tagged (headings as `#`, lists as `-`, etc.), which saves us post-processing.
- Quality ceiling is the highest of any open-source tool we looked at.

**Weaknesses for our case.**
- Requires Python 3.10+. Our venv is 3.9 and `marker_single --help` currently crashes:
  ```
  File ".venv/lib/python3.9/site-packages/surya/schema.py", line 143
    languages: List[str] | None = None
  TypeError: unsupported operand type(s) for |: '_GenericAlias' and 'NoneType'
  ```
- Installs ~2 GB of PyTorch + transformers + Surya weights on first run.
- CPU-only runs are slow: ~30–60 s per page on a modern laptop. For a 270-page book this is 2+ hours.
- Over-segments short pages: title pages and JSTOR front matter sometimes get split into dozens of tiny "text" regions.

**What we can borrow.**
- Marker's reading-order model validates the intuition that column reconstruction is fundamentally a geometric / ordering problem, not a text one. Our PyMuPDF word-level approach is the "poor man's" version of the same idea.
- Its post-processing rules for joining wrapped lines, handling hyphenation, and stripping running headers are worth lifting into `clean_text` — especially the hyphenation join (we currently mishandle "Organiza-\ntion" in bibliographies).

**Verdict.** The correct target for a `--papers` power-user flag, not the default. We should wire it so that users on Python 3.10+ can opt in and get the ceiling, but the default has to work in 3.9.

---

## GROBID

**Approach.** Java/Scala pipeline built on CRF (Conditional Random Fields) models trained on scientific-paper layouts. It tokenizes the PDF via pdfalto (a fork of pdftohtml), builds features from each token's position, font, and neighborhood, then labels tokens with one of {title, author, affiliation, abstract, section header, body, figure caption, reference, etc.}. Sequences of labeled tokens become structured TEI-XML output.

**Strengths.**
- Gold standard for metadata and reference extraction — title, authors, affiliations, and a fully structured bibliography with DOIs where possible.
- Mature (10+ years), actively maintained, heavy research usage.
- Handles multi-column layouts well because the CRF sees each token's x/y and learns that a column gap is a strong separator feature.
- Good at distinguishing body from running headers, page numbers, footnotes.

**Weaknesses for our case.**
- Java-only. Runs as a server (`./gradlew run` spins up a Jetty on :8070) and clients talk HTTP to it. Bringing that into a Python `convert.py` means shipping a Dockerfile or asking users to install Java 11+.
- TEI-XML output needs a separate markdown-conversion step. Not a huge amount of code but non-trivial.
- Trained primarily on modern scientific papers (STEM, IEEE/Elsevier layouts). Less accurate on 1950s social-science JSTOR scans, which is most of our corpus.
- Full-text body extraction is correct but not as clean as marker — it does less line-joining and paragraph smoothing.

**What we can borrow.**
- GROBID's metadata confidence scores (title, author, year) could be a signal for auto-detecting "this is an academic paper" — far more robust than our current "does it have a DOI in the text?" approach. But we'd need to extract those signals some other way since we can't ship GROBID in-process.
- Their feature set for labeling tokens is a good mental model: use x-position, y-position, font size, font name, relative position on the page, and neighborhood stats. Our current gutter detection uses only x; adding font-size clustering would help us tell headers from body on pages where the column gap is ambiguous.

**Verdict.** Not worth integrating directly. Too heavy. Useful as a mental model and as something to point users at if they need high-quality reference extraction specifically.

---

## Nougat (Meta)

**Approach.** End-to-end vision transformer that treats the paper as an image and generates markdown tokens directly. Trained on arXiv source code paired with rendered PDF pages, so the model learned to output LaTeX-adjacent markdown for equations, tables, and section structure.

**Strengths.**
- Best-in-class equation and table extraction. It outputs `\begin{equation} ... \end{equation}` and structured tables in Markdown form.
- Column layout is a non-issue because the model sees the rendered page and generates reading-order output.
- Single model, no separate layout + OCR + parsing steps.

**Weaknesses for our case.**
- GPU required for reasonable throughput. CPU inference is ~2–5 min per page.
- Model weights are ~1.4 GB (base) or ~3.5 GB (large).
- Trained almost exclusively on arXiv (math/CS/physics). Hallucinates on old social-science scans, especially on serif fonts with heavy kerning. Known to skip paragraphs or invent section headers on low-quality inputs.
- Maintenance is uneven — Meta paused active development in 2024.

**What we can borrow.**
- The validation lesson: an ML model that never saw 1950s JSTOR scans will underperform our deterministic PyMuPDF approach on this corpus. Good reminder not to chase "the ML tool will solve it" without a matching training distribution.
- Nothing directly actionable for our pipeline.

**Verdict.** Wrong tool for our corpus. Would be a great choice if we were processing arXiv math preprints.

---

## science-parse

**Approach.** Allen AI's metadata extractor, primarily for CS papers. Java-based. Uses heuristics plus a trained CRF similar to GROBID for title / author / abstract / references. Explicitly does NOT extract full body text — just metadata.

**Strengths.**
- Lightweight compared to GROBID.
- Known-good reference extraction for arXiv-era CS.

**Weaknesses for our case.**
- Java. Same integration cost as GROBID.
- No body-text extraction at all, so doesn't solve any of our three known issues.
- Largely abandoned — last meaningful commits in 2020. Allen AI shifted focus to [S2ORC](https://github.com/allenai/s2orc) + other newer tools.

**What we can borrow.**
- Nothing directly — it doesn't touch the column-layout problem.

**Verdict.** Not applicable. Skip.

---

## CERMINE

**Approach.** Java tool from CEON (Poland). Uses a cascade of CRF + rule-based heuristics, similar architectural family to GROBID but pre-dates it. Extracts metadata, references, and a rough body text. Built on iText and its own PDF parser.

**Strengths.**
- Another metadata extractor with good reference parsing.
- Permissive license, has been used in production ingest pipelines (e.g., CORE, OpenAIRE).

**Weaknesses for our case.**
- Java + Maven build. Not runnable in-process from Python.
- Less actively maintained than GROBID.
- Body text extraction is decent but not marker-level.

**What we can borrow.**
- Nothing directly. Mostly a historical GROBID alternative.

**Verdict.** Skip. GROBID covers this role better if we ever need Java-based metadata extraction.

---

## pdffigures2

**Approach.** Scala tool from Allen AI, specifically for extracting figures, tables, and their captions from scientific papers. Does not produce body text output.

**Strengths.**
- Best-in-class figure extraction.
- Pairs figures with their captions reliably.

**Weaknesses for our case.**
- Doesn't extract body text at all.
- Scala / JVM.

**What we can borrow.**
- Nothing — orthogonal to the column-layout problem we're solving. Could be a future addition if we start wanting to include figures in the markdown output.

**Verdict.** Skip for the current task.

---

## unstructured.io

**Approach.** Python library (Unstructured.io open-source core, plus a paid hosted API). The PDF path tries a cascade: first attempt text extraction via pdfplumber, then fall back to layout-aware extraction using an OCR model + layout detection (either from their own hosted API or a local detectron2 install). Produces element-typed JSON: `Title`, `NarrativeText`, `ListItem`, `Table`, `Header`, `Footer`, etc.

**Strengths.**
- Python-native, pip-installable.
- Element typing is genuinely useful for downstream LLM prompts — same idea as marker's semantic tags.
- Active development with commercial backing.
- The `partition_pdf(strategy="hi_res")` mode uses detectron2 for layout detection, which handles columns well.

**Weaknesses for our case.**
- The "fast" strategy (no ML) uses pdfplumber and has NO column awareness — it would produce the same interleaving we currently see.
- The "hi_res" strategy requires detectron2, which is a pain to install (needs a matching CUDA / torch version) and adds ~1 GB of weights.
- The license is Apache 2.0 for core but the hosted API is commercial; some features silently degrade if you don't have keys.
- Hit-or-miss on older / non-STEM papers. We'd need to test on our corpus.

**What we can borrow.**
- The element-typing idea is worth adding to BookConvert's post-processing: when we emit a line, we already know from geometry whether it's a running header, body, or full-width block. We could expose that as semantic markdown (H1/H2/H3) more systematically.
- Their fallback cascade (fast → hi_res → OCR) is a good pattern for BookConvert's existing `pymupdf → marker → ocr` structure.

**Verdict.** A viable alternative to marker for users who prefer a more mainstream Python dep. Worth a mention in the decision doc but not worth making it the default when marker is available.

---

## pdfplumber

**Approach.** Python wrapper around pdfminer.six. Exposes per-character geometry (bbox, font, size, color), per-word aggregations, and ruling-line detection. No layout analysis of its own — you write the column logic.

**Strengths.**
- Pure Python, runs in our existing 3.9 venv.
- Clean API for getting every character's x/y/width/font.
- Very good at detecting rule lines (horizontal/vertical), which helps with tables.
- Widely used, stable, well-documented.
- Fast (~10x faster than marker, comparable to PyMuPDF).

**Weaknesses for our case.**
- We have to write the column detection ourselves — pdfplumber doesn't have it built in.
- No paragraph-break heuristic, no header detection, no reading-order solver.
- pdfminer.six is slower than PyMuPDF's C++ backend on large books.

**What we can borrow.**
- Font-size and font-name clustering. PyMuPDF exposes the same via `get_text("dict")`, but pdfplumber's docs are the clearest reference for the idiom: group characters by font, use size as a header/body discriminator, use x-position bimodality as a column discriminator.
- The column extraction recipe in the pdfplumber docs is essentially: compute a vertical histogram of character x-positions, find local minima, those are column gaps. We can implement the same histogram approach in PyMuPDF and it would be more robust than our current "scan x values near the midpoint" heuristic.

**Verdict.** Not worth a full migration away from PyMuPDF — they expose the same primitives and PyMuPDF is faster. But the histogram-based column detection is a clear improvement we should bring into our word-level detection.

---

## Adobe PDF Extract API

**Approach.** Adobe's commercial API. Hands the PDF to Adobe's internal layout engine (the same one that Acrobat uses for reflow and "export to Word"). Returns structured JSON with per-element content, reading order, tables, and figures.

**Strengths.**
- Adobe has the best PDF layout analysis in the industry, period. They have decades of heuristics and proprietary ML tuned on every weird PDF in existence.
- The reading-order output is essentially ground-truth.
- Native table extraction.

**Weaknesses for our case.**
- Commercial. Free tier is 500 documents / month, paid after.
- Network-dependent. A CLI tool that requires an internet round-trip per file is friction for a bulk batch.
- No on-prem option unless you pay for enterprise Adobe Experience Manager.
- Vendor lock-in.

**What we can borrow.**
- Reading-order solver design notes from [their public documentation](https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/): they describe reading order as a graph problem where each element is a node and edges are geometric adjacency constraints, then topologically sort. Our current "sort by y, tiebreak by x with special handling for columns" is a simpler version of the same idea.
- Not worth integrating directly.

**Verdict.** Skip. Commercial API is overkill for a self-hosted converter for a personal research archive.

---

## Cross-cutting takeaways

1. **Column layout is a geometric problem, not a text problem.** Every serious tool either (a) trains an ML model on page pixels, or (b) uses per-token x/y/font-size features and a learned or hand-rolled classifier. Our current word-level gutter detection is approach (b) — it just needs to be more robust.

2. **Font-size and font-name are the most under-used signals.** GROBID, marker, and pdfplumber all use them heavily; our current code uses only x/y. A body paragraph and a section header might have the same y-coordinate but different font sizes, and font size is the cleanest way to distinguish them. We should extend `_extract_page_text` to look at span fonts when a block is ambiguous.

3. **The histogram-based gutter detector is better than point-sampling.** Our current detection scans x from `mid - 15%` to `mid + 15%` at 2pt steps and picks the best-coverage x. A histogram (count character occurrences per x-bucket across the whole page) finds the gutter as a clear local minimum and also detects 3-column layouts automatically. This is cheap to implement and strictly better.

4. **Paragraph breaks don't need a big model.** The heuristics every tool uses are the same: (a) first-line indent > threshold, (b) y-gap between consecutive lines > 1.3× line-height, (c) previous line ends with sentence-terminal punctuation and new line starts with a capital, (d) new line's first span uses a bold/heading font. We already do some of this in `clean_text`; we can lift (d) from the dict extraction.

5. **Hyphenation joining is universally done.** Every tool joins `word-\nrest` → `wordrest`. Our current output has un-joined bibliography entries like `Organiza-\ntion` which is a trivial post-processing miss, not a column problem.

6. **Reading-order solvers are almost always "columns top-to-bottom, within column y-sort, full-width elements split into sections".** That matches what I implemented in `_extract_page_text`. The main gap is: what do we do with a full-width element that sits *between* column content (not a header or footer)? Adobe and marker solve this by splitting the columns into "sections" bounded by full-width elements. Our code uses a simpler rule (inline full-width goes after the left column, before the right). Good enough for 95% of cases; we should remember this limitation.

---

## Specific recommendations for BookConvert

1. **Default path stays PyMuPDF + our enhanced column detection** (Approach B). It works in Python 3.9, has no external deps, and already handles 43/43 of our corpus as of the checkpoint commit.

2. **Add a `--papers` / `--method marker` opt-in** for users on Python 3.10+ who want the quality ceiling. Detect the Python version and print a clear error if marker is invoked on 3.9.

3. **Auto-detection heuristic for the `--papers` path is optional** because the user can explicitly flag it. If we want it, the strongest signals are:
   - `doc.metadata.get("subject")` or `creator` contains "LaTeX", "TeX", "arxiv", or a journal name
   - `/Producer` field contains a known publisher (Elsevier, Sage, Oxford, Wiley)
   - ≥ 50% of pages have 2-column detection hits via our new `_detect_two_column_split`
   - Page count ≤ 60 (papers are short; books are long — filters out the one book in the test corpus, "The Reflective Practitioner" at 276 pages)

4. **Short-term improvements to pull into our word-level detection** (do-able in the current iteration loop):
   - Histogram-based gutter detection (more robust than point-sampling)
   - Hyphenation joining in `clean_text` (fixes bibliography entries)
   - Font-size-based header promotion (fixes cases where a full-width section heading gets misclassified as body)

5. **Do not adopt** Nougat, science-parse, CERMINE, pdffigures2, Adobe. Each is either wrong for the corpus, wrong for the runtime constraints, or commercial.
