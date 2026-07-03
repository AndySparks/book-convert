---
type: decision
date: 2026-07-03
last_updated: 2026-07-03
slug: post-conversion-cleanup
status: accepted
scope: bookconvert
tags: [cleanup, extraction-artifacts, verbatim-fidelity, default-behavior]
supersedes: []
invalidates: []
ceremony: y-statement
---

# BookConvert runs a verbatim-safe cleanup pass by default

In the context of two Virginia Tufte books (*Grammar as Style*, *Artful
Sentences*) being converted on 2026-07-03 and needing an extensive manual
cleanup afterward — hundreds of dropped-space function-word joins
("thefrozen", "sucha"), stray-consonant citation ghosts ("—wWilliam"),
picture-text garble blocks, and mangled headings — none of which any backend
repairs and none of which the quality scorer even flagged (both books scored
`quality_score: 1.0` with zero warnings), and facing the choice between (a)
leaving cleanup as a manual post-step done by hand each time, (b) shipping the
cleanup logic behind an opt-in `--clean` flag, or (c) **running the cleanup
pass by default on every conversion with a `--no-clean` escape hatch** — we
chose (c), so the tool produces clean output out of the box, over (a) which
repeats fragile manual work per book, and (b) which leaves the default output
carrying artifacts the tool already knows how to fix.

## Why default-on is safe

Default-on raises the bar: a bad automated split would silently corrupt every
future book. The de-join is therefore built for **precision over recall** and
governed by verbatim fidelity — it must never mangle a real word, especially
inside a quoted passage.

- It only splits at a **whitelisted function-word boundary** and only when the
  whole token is not a dictionary word. Traps that have no function-word split
  point (`aeroplane`, `manservants`, `givenness`, `moocow`) are never touched.
- Short leading function words that begin real words (`at`→"at taches",
  `off`→"off ate") are excluded from the leading whitelist.
- British `-our`/Latin `-us` endings are guarded (`colour` never becomes
  "col our").
- A trailing `a`/`an` on a short stem is rejected so proper nouns survive
  (`lowa`, an OCR of "Iowa", is not split into "low a").

Validated against the two real books: 190–212 joins restored per book with
zero false splits; `moocow`, `colour`, and `Iowa` all preserved. The
dictionary-free repairs (stray consonants, picture-text) carry no such risk.

## What changed

1. **New `cleanup.py` module** — `clean_markdown(text) -> (text, stats)`,
   idempotent and verbatim-safe. Encodes the de-join, stray-consonant, and
   picture-text repairs with the guards above.
2. **`convert_book` runs it by default** on every backend's markdown output
   (`--no-clean` to skip), recording `cleaned` + `cleanup` stats on the report
   sidecar.
3. **Image-path bug fixed** in the `pymupdf4llm` backend: it embedded the full
   `image_path` (output-dir-prefixed, sometimes absolute) as the ref prefix,
   breaking image links relative to the markdown file. Refs are now rewritten
   relative to the markdown, matching the default pymupdf backend.
4. **`pyspellchecker` added to `requirements.txt`** for the de-join step. The
   default install is no longer PyMuPDF-only, but the dependency is
   pure-Python (no native build) and cleanup degrades gracefully if it is
   absent.
5. **Tests**: `tests/test_cleanup.py` (de-join splits + guards, stray
   consonants, picture-text, idempotency) and an image-ref regression test in
   `tests/test_pymupdf4llm_backend.py`.

## Known limitations

- The de-join needs a dictionary; without `pyspellchecker` that step is
  skipped (a warning is recorded) and only the dictionary-free repairs run.
- Precision-first means some genuine joins are left unsplit rather than risk a
  wrong split — notably ambiguous OCR (`offrom`) and any join whose split
  would produce a plausible-but-wrong reading. Deeply garbled OCR regions are
  left intact rather than reconstructed (that would be fabrication).
- Contextual, semantic fixes (a mis-OCR'd `lowa` → `Iowa`, a wrong chapter
  number) are out of scope for an automated pass and remain manual.
