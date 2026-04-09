# Quality-Gated OCR Auto-Fallback Design

**Issue:** AndySparks/book-convert#17
**Date:** 2026-04-09
**Status:** Design approved, ready to plan implementation

## Problem

`convert_with_pymupdf` has an existing quality gate and an existing OCR auto-fallback, but they only catch one failure mode: PDFs where extraction yields little or no text (fully-scanned docs). A second failure mode is silently passed through: PDFs whose fonts decode to garbage while still producing extractable text.

Observed in the wild: _The Pyramid Principle_ by Barbara Minto. Every page yields text, but it contains pervasive font-encoding artifacts (`vv` for `w`, `tn` for `m`, `n1` for `m`, `fr` for `f`, etc.). Example:

> The Minto Pyra1nid Principle is applicable to any docun1ent in which your purpose is to present your thinking clearly.

The output is technically readable but degraded enough to be a poor source for LLM ingestion, which is the whole point of the tool. Re-running the file with `--method ocr` produces clean output, so the fallback works; we just never take it.

## Goal

Detect degraded-but-nonempty pymupdf extractions and auto-fall-back to OCR, reusing the existing `auto_ocr` mechanism in `convert_pdf`.

## Non-goals

- **No pattern-based ligature decoding.** Substitutions like `vv` → `w` or `n1` → `m` are brittle and risk silently corrupting legitimate text. The quality gate routes around the problem by switching extraction methods entirely.
- **No blocking when OCR is unavailable.** The existing `DependencyError` path in `convert_pdf` already handles that: it prints a warning and returns False.
- **No new CLI flag.** The gate is always on; opt-out is not needed since the worst case is "conversion takes longer and produces better output."

## Design

### Components

#### 1. `_load_english_wordlist()` — new lazy loader

Module-level cached function returning a `frozenset[str]` of lowercased English words.

- Try `/usr/share/dict/words` first. Split on newlines, lowercase, filter to alphabetic tokens of length ≥ 2, freeze.
- If the file is missing or unreadable, fall back to a bundled `_FALLBACK_WORDLIST` — a hand-curated frozenset of ~500 of the most common English words plus common management/business vocabulary (to match the corpus this tool gets pointed at).
- Log at DEBUG which source was used.

The lazy loader pattern avoids reading ~2MB at import time when the function isn't called (e.g. clean-only mode).

#### 2. `_text_quality_score(text, sample_size=2000)` — new scorer

Returns a float in `[0.0, 1.0]` representing the fraction of sampled tokens that appear in the English wordlist. Higher is better.

Algorithm:

1. Strip markdown syntax characters (`#`, `*`, `-`, `<!--`, `-->`, `|`, backticks) so headings/bullets don't contribute garbage tokens.
2. Tokenize on whitespace.
3. For each token, strip leading/trailing punctuation (`.,;:!?"'()[]` and similar). This preserves words like `word,` and `"word"` as `word`.
4. Keep only tokens that are purely alphabetic after stripping and of length ≥ 3. This excludes short words where ligature artifacts cluster (`vv`, `tn`, `n1`) and single-letter noise.
5. If fewer than 100 tokens remain, return 1.0 (refuse to judge — too little text, could be a pamphlet or image-heavy doc).
6. Sample up to `sample_size` tokens from the filtered list. Use deterministic sampling (first N) rather than random — reproducibility matters for debugging and tests.
7. Count how many sampled tokens (lowercased) appear in the wordlist.
8. Return `matches / sampled`.

#### 3. Quality check in `convert_with_pymupdf`

After the writing loop closes the output file, but before the existing `MIN_TEXT_RATIO` check:

```python
quality = _text_quality_score(output_file.read_text(encoding="utf-8", errors="replace"))
log.debug("Text quality score: %.3f", quality)
if quality < QUALITY_THRESHOLD:
    output_file.unlink(missing_ok=True)
    raise ConversionError(
        f"Low quality text extraction (score: {quality:.2f}, threshold: {QUALITY_THRESHOLD}). "
        f"This PDF may have non-standard font encoding. Try: --method ocr"
    )
```

`QUALITY_THRESHOLD` is a module-level constant, calibrated below.

#### 4. Broaden `auto_ocr` trigger in `convert_pdf`

Line 1505 currently reads:

```python
if auto_ocr and method != "ocr" and "scanned" in str(e).lower():
```

Change to:

```python
error_msg = str(e).lower()
if auto_ocr and method != "ocr" and ("scanned" in error_msg or "low quality" in error_msg):
```

This reuses the entire existing fallback path (dependency check, partial-file cleanup, error handling) without duplicating logic.

### Calibration

`QUALITY_THRESHOLD` will be calibrated empirically during implementation by scoring three existing outputs:

| File | Expected | Method used |
|---|---|---|
| `The Human Side of Enterprise, Annotated Edition.md` | High (well above threshold) | pymupdf |
| `The-Functions-Of-The-Executive.md` | High (well above threshold) | OCR |
| `The Pyramid Principle.md` | Low (well below threshold) | pymupdf |

Target: threshold lands with a ≥ 0.15 margin on each side of the gap. If no clean separation exists, escalate back to design — the scorer needs rethinking.

The calibration numbers and the chosen threshold go into a module-level comment next to `QUALITY_THRESHOLD` so future readers know why it's set where it is.

### Testing

No existing test infrastructure in this repo. We'll add a minimal `tests/` directory with `pytest`.

New file `tests/test_quality.py`:

| Test | What |
|---|---|
| `test_quality_clean_english` | Clean English paragraph, score ≥ 0.7 |
| `test_quality_mangled_text` | vv/tn/n1-mangled paragraph, score < threshold |
| `test_quality_short_text_passes` | < 100 tokens returns exactly 1.0 |
| `test_quality_wordlist_fallback` | Monkeypatch `/usr/share/dict/words` missing, scorer still works via fallback |
| `test_quality_strips_markdown` | Markdown syntax doesn't affect score |

We don't test `convert_with_pymupdf` end-to-end — that requires a real PDF fixture. Instead, unit test the scorer and trust the integration via manual verification on the three real files.

Add `pytest` to `requirements.txt` under a dev extras marker, or a separate `requirements-dev.txt`. Add `make test` target if a Makefile exists, otherwise document `python -m pytest tests/` in the README.

### Error messages and logging

- INFO-level log when the quality gate triggers: `"Text quality 0.34 below threshold 0.55; retrying with OCR..."`
- DEBUG-level log always: `"Text quality score: 0.XX"`
- User-visible stdout message from the existing auto_ocr retry code already prints `"Text extraction failed, auto-retrying with OCR..."`; we don't need a new one.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Wordlist fallback too small, false positives on good text | Use `/usr/share/dict/words` when available (2MB, comprehensive); only fall back on non-Unix systems |
| Legitimate non-English text flagged as bad | Accept this. Tool's target corpus is English management/business books. A `--lang` flag can be added later if needed. |
| Threshold calibration doesn't cleanly separate good/bad | Escalate: rethink the scorer (e.g. add bigram analysis). Do not ship a threshold that overlaps. |
| OCR adds minutes to every bad extraction | Acceptable. Bad extractions are rare (1 of 3 in today's batch). |
| Quality check re-reads the output file from disk | Fine. File is already written; read is fast. Alternative (pass text through in memory) would restructure the writing loop unnecessarily. |

## Rollout

Single commit on `main`:
1. Add `_load_english_wordlist`, `_text_quality_score`, `QUALITY_THRESHOLD` to `convert.py`
2. Add quality check call in `convert_with_pymupdf`
3. Broaden `auto_ocr` trigger in `convert_pdf`
4. Add `tests/test_quality.py`
5. Add pytest to requirements
6. Update README with test instructions

No migration, no config, no breaking changes. Existing users get strictly better behavior.
