---
type: decision
date: 2026-08-17
status: accepted
tags: [marker, ocr, quality, dependencies]
---

# marker 2.0 is the floor

## Decision

`requirements-marker.txt` pins `marker-pdf>=2.0.0`, and the install docs name the
`llama.cpp` system dependency that 2.x needs and pip cannot supply.

## Why: 1.10.2 writes text that was never in the book

Handed a blank page — a part-divider verso, a half-title, an unnumbered leaf — marker
1.10.2 has nothing to transcribe and does not stop. It emits a repeating n-gram until
it reaches a token cap, producing about **2,046 characters of prose-shaped text**:

```
The state of the state of the state of the state of the state of the state ...
and House and House and House and House and House and House and House ...
```

Measured over one corpus of 955 converted sources, **16 books carried 44 such
passages.** They survive every gate that reads structure rather than prose: pagination
stays coherent, figures still resolve, the quality score is unaffected.

The danger is not that the text is obviously garbage. It is that it *sits in a filed
source as if it were the book*, and anything reading that file — a person, a quote
checker, a model — has no way to know the difference without being told to look.

## Why 2.0 fixes it

Verified rather than assumed. Both books were converted twice at the same page ranges,
under 1.10.2 as a control and under 2.0.0:

| book | 1.10.2 (control) | 2.0.0 |
|---|---|---|
| Grove, *High Output Management* | 12 degenerate lines reproduced | clean |
| Cringely, *Accidental Empires* | 8 degenerate lines reproduced | clean |

The control arm is the load-bearing half. A clean 2.0 result proves nothing unless the
failure reproduces under the version that produced it — and on a third book (a single
near-blank page) it did **not** reproduce, which is exactly why one book would have been
insufficient evidence.

**The root cause turns out to be simpler than "a token cap."** Every affected page is
blank or near-blank, and 2.0 emits *nothing* on those same pages while returning full
text on content pages in the same run. 1.10.2 was not corrupting prose; it was
inventing it where there was none.

Consequence worth recording: **no reconversion was needed for content recovery.** All 14
wholly-noise pages across those 16 books were blank leaves. What 1.x produced was
additive junk, not lost text.

## The dependency, which is a trap either way

marker 2 runs Surya OCR 2 through a llama.cpp backend on CPU and MPS, and aborts with
`SpawnError: llama-server binary not found` without it. That crash arrives at the **end**
of a long conversion.

This was already live before this decision: `requirements-marker.txt` pinned no version,
so anyone installing fresh already got 2.x and then hit an unexplained crash with nothing
in the README about it. Pinning the floor does not create the dependency; it documents
one that was already reaching people.

## Compatibility

Every flag `convert.py` passes to marker exists in 2.0, checked against its `--help`
rather than assumed: `--paginate_output`, `--keep_pageheader_in_output`,
`--keep_pagefooter_in_output`, `--disable_image_extraction`, `--output_dir`. The
`{N}------` page separator that `_MARKER_PAGE_SEPARATOR_RE` parses is unchanged, and
page indices are stable — of ten Cringely pages probed, the eight carrying a readable
folio gave the same value at the same sheet under both versions, at a constant offset of
13. The other two carry no folio under either version.

That last check mattered more than the others. A rewritten layout model could have moved
where page breaks land, and a shifted page map would have silently invalidated every
printed-page citation into that book while looking perfectly healthy.

## Consequences

- Existing `.venv-marker` installs on 1.x must be upgraded, and `brew install llama.cpp`
  added. Nothing detects a stale venv; the symptom is silent, and it is old conversions
  looking fine.
- Conversions produced under 1.x are not retroactively suspect in their *prose*, but may
  carry the blank-page passages. `mc-wiki/tools/check-degenerate-text.py` finds them.
- marker 2 defaults to `fast` mode on CPU/MPS and `balanced` on GPU. Only the CPU/MPS
  default was exercised here; it produced correct text on content pages. `balanced` is
  untested in this repo.
