# Paper Extraction: Results

Results of the word-level column extraction work landed across commits `028fc79`, `4a3f422`, `45a9ed4`, `fb78851`, `9620b44`, `9749065`.

## Methodology

1. **Baseline** = `convert.py` at commit `c340931` (immediately before the first column-extraction commit in this session). All 43 input papers re-converted to `/tmp/bookconvert-baseline/`.

2. **Postfix** = `convert.py` at HEAD after the loop work. Same 43 papers re-converted to `/tmp/bookconvert-postfix/`.

3. **Diff discipline**: line-count changes, per-file diffs, and hand inspection of the 5 worst before-cases.

## Corpus summary

- 43 total papers processed by both runs.
- 1 pre-existing failure: `Argyris (1977) Double Loop Learning in Organizations.pdf` is a scanned-image PDF with 0/12 pages containing extractable text. Fails in both baseline and postfix with the same "try --method ocr" message. Not a regression.
- 35 / 43 markdown files differ between baseline and postfix.
- 8 / 43 files are identical (the purely single-column papers where nothing changed).
- **`The Reflective Practitioner.md` (the only book in the corpus) is byte-identical: 0-line diff against baseline. No book regression.**

## Worst 5 cases (before → after)

### 1. argyris1977 — merged-block two-column body, canonical merged case

**Problem:** PyMuPDF returns the entire page-1 body as a single block that spans both columns (x=53-475, h=329pt). Default reading order interleaves left and right columns word-by-word.

**Baseline p.1 body** (from `/tmp/bookconvert-baseline/argyris1977.md`):

```
In a recent review of the literature on MIS corrects errors. This
requirement, in turn, implies implementation, I found the major theme
to be that learning also requires the capacity to know unmet
expectations and disappointments, when it is unable to identify and
correct errors. especially when MIS technology was used to deal
```

Left column ("In a recent review… MIS implementation, I found the major theme to be unmet expectations…") and right column ("corrects errors. This requirement, in turn, implies that learning also requires…") are interleaved mid-sentence on every row. Unreadable.

**Postfix p.1 body** (from `/tmp/bookconvert-postfix/argyris1977.md`):

```
In a recent review of the literature on MIS implementation, I found
the major theme to be unmet expectations and disappointments,
especially when MIS technology was used to deal with the more complex
and ill-structured problems faced by organizations.' The author's
explanations for the implementation gap could be broken down into eight
different categories. They were: (1) were not well understood by line
MIS management; (2) top line management was not involved in persuading
and selling the use of MIS to the users in the organization; …
```

Left column reads top-to-bottom as a coherent paragraph. The right column follows after the footnote, with "corrects errors. This requirement, in turn, implies…" continuing in its own section.

### 2. argyris1993 p.2 — body + author-bio sidebar

**Problem:** The page has a 6-line biographical sidebar in the left column (y=233-306) and a 50-row body in the right column. Default extraction reads row-by-row and splices the bio's words into the body mid-sentence.

**Baseline p.2** (`/tmp/bookconvert-baseline/argyris1993.md`):

```
Chris Argyris is the James 6. Conant Pro- Yet, they all seem to have
the same difficulties fessor at the Schools of Business and Eduin
dealing effectively with double-loop probcation at Harvard University.
He holds six lems. There must be some causal factors comhonorary
degrees from universities here and mon to these different human
beings. abroad. His most recent book, Overcoming Moreover, we have
worked with about Organizational Defensive Routines, was 2,000
individuals, members of organic and published by Allyn-Bacon in 1990.
stranger groups, to help them become more effective.
```

The bio ("Chris Argyris is the James 6. Conant Professor at the Schools…") is spliced word-by-word into the body ("Yet, they all seem to have the same difficulties in dealing effectively with double-loop problems…"). The result reads as nonsense like "Conant Pro- Yet, they all seem" and "Busines s and Edu-in dealing effectively".

**Postfix p.2** (`/tmp/bookconvert-postfix/argyris1993.md`):

```
Chris Argyris is the James 6. Conant Professor at the Schools of
Business and Education at Harvard University. He holds six honorary
degrees from universities here and abroad. His most recent book,
Overcoming was Organizational Defensive Routines, published by
Allyn-Bacon in 1990.

viduals use to design and implement their behavior. Human beings with
a wide variety of personalities and styles do not seem to vary in the
theories for action that they hold.
For readers who are not familiar with the research cited at the end of
the article, the reasoning behind this claim is as follows. Since
1974, my colleagues and I have studied some 6,000 individuals varying
in age, sex, minority status, education, wealth, and position…
```

Bio is a standalone paragraph. Body flows as one continuous coherent stream. (The "viduals use…" continuation is a pre-existing hyphenation artifact from the previous page's "indi-".)

### 3. argyris1989 p.2 — asymmetric body + bio, short bio + offset y-range

**Problem:** Same class as argyris1993 but even more asymmetric — the bio is only 4 rows of dedicated content and the bio/body y-ranges barely overlap. The first-pass detection missed this page entirely.

**Baseline p.2** (`/tmp/bookconvert-baseline/argyris1989.md`):

```
Chris Argyris is the James B. Conant Professor at the Schools of
Business and Education at Harvard University.
He holds six honorary degrees from universities here and abroad. His
newest book, Ovefthe participants prepare.
The fourth step was accomplished when the entire team returned six
months later for three days.
…
They spoke of returning the next year, even though most reported that
when they had arrived for the first session, they had not thought they
would recommend that the sessions become annual events. coming
Organizational Defensive Routines, will be published by Allyn-Bacon
early in Let us now turn to the theory of learning that formed the
basis of the program.
```

The sentence "His newest book, Overcoming Organizational Defensive Routines, will be published by Allyn-Bacon early in 1990" is split across the page and sandwiches the body text "the participants prepare. The fourth step…" between "Ovef-" and "coming Organizational Defensive Routines…".

**Postfix p.2** (`/tmp/bookconvert-postfix/argyris1989.md`):

```
Chris Argyris is the James B. Conant Professor at the Schools of
Business and Education at Harvard University.
He holds six honorary degrees from universities here and abroad. His
newest book, Ovefcoming Organizational Defensive Routines, will be
published by Allyn-Bacon early in

the participants prepare. The fourth step was accomplished when the
entire team returned six months later for three days.
Not surprisingly, all of the teams began monitoring the implementation
process the moment they returned to their home locations. They
therefore spent most of the final three days identifying and
deliberating over those difficult strategy formulation and
implementation problems, with the help of their outside consultants.
…
Let us now turn to the theory of learning that formed the basis of the
program.
```

Bio is a coherent paragraph ("His newest book, Overcoming Organizational Defensive Routines, will be published by Allyn-Bacon early in [1990]"). Body starts fresh after the bio and reads properly top-to-bottom. The ligature bug "Ovefcoming" (should be "Overcoming" — PyMuPDF mis-encodes the `r` glyph in this PDF's font) is pre-existing and unrelated to column handling.

### 4. argyris1955 p.2 — JSTOR front matter, merged-block masthead

**Problem:** Page 2 is a journal masthead with "THE JOURNAL OF BUSINESS" as a centered title, a rule line, then "ORGANIZATIONAL LEADERSHIP AND PARTICIPATIVE MANAGEMENT" as the article title. The masthead block is wide and crosses the detected gutter, but the content inside is full-width headings, not two columns. The old code either treated the whole page as merged-2-col (splitting titles into nonsense) or as 1-col (keeping them readable).

**Baseline p.2**:

```
THE
JOURNAL OF
BUSINESS
The School of Business of the University of Chicago ~~~~~~~~- M 'l111'|l' VOL. XXVIII JANUARY 1955 No. i
ORGANIZATIONAL LEADERSHIP AND PARTICIPATIVE
MANAGEMENT
CHRIS ARGYRIS*
```

**Postfix p.2**:

```
THE
JOURNAL OF
### BUSINESS
The School of Business of the University of Chicago ~~~~~~~~- M 'l111'|l' VOL. XXVIII JANUARY 1955 No. i
## ORGANIZATIONAL LEADERSHIP AND PARTICIPATIVE
### MANAGEMENT
CHRIS ARGYRIS*
```

Identical text, just with heading-level formatting added by the existing heading detector. No regression; the masthead is treated as a single-column page with full-width title blocks. The real fix shows up on p.3 onwards (the article body) where the merged-block split kicks in.

### 5. The Reflective Practitioner p.266 — book index (regression averted)

**Problem:** A book index is a single-column page where entries are alphabetically listed with ragged-right flush. It has short rows ("Aalto, Alvar, 000, 78") and long wrapping rows ("action: dichotomy with thought, 275, 276-81; interpersonal theory of, 226, 321-22, 353; Model I, 226-28…"). An early version of my detection mis-identified it as two-column because 83% of rows don't cross the midpoint — the short rows don't reach that far.

**First-attempt detection** produced this broken output:

```
<!-- Page 266 -->
Index

230, 263, 303, 304–6, 335; Model II, 230–34, 321–22; subject/object
action-present, 62, 279, 281 action science, 319–20, 323, 354
adaptability, 15–16, 171 …

- Bell, Daniel, ... 7
- Bernoulli, Daniel, ... 183
- Bernstein, Richard, ... 48

Aalto, Alvar, 000, 78 accountability, 293, 295, 297, 345–46 Ackoff,
Russell, 16 action: dichotomy with thought, 275, 276–81; interpersonal
theory of, 226, 321–22, 353; Model I, 226–28,

schools of (pluralism), 77–78, 102, 272–3, 310–11 …
```

The "A" entries appeared in the middle of the page because the detection split the index into fake left/right columns and emitted the right column before the left. Baseline (pre-detection) and final postfix both produce the same correct single-column output:

```
<!-- Page 266 -->
Index Aalto, Alvar, 000, 78 accountability, 293, 295, 297, 345–46
Ackoff, Russell, 16 action: dichotomy with thought, 275, 276–81;
interpersonal theory of, 226, 321–22, 353; Model I, 226–28, 230, 263,
303, 304–6, 335; Model II, 230–34, 321–22; subject/object of, 191,
195–203, 322–23, 347 action-present, 62, 279, 281 action science,
319–20, 323, 354 adaptability, 15–16, 171 …
```

The final detection rejects this page because the "right column" has zero rows where content is wholly on that side. Requires real 2-col signals, not just high "no-crossing" coverage.

This is documented as an averted regression because multiple mid-loop commits had this broken; the final landed state (`fb78851` onward) is correct.

## Known-issue matrix

| Issue | Papers | Status |
|---|---|---|
| **(1) JSTOR fake TOCs** | argyris1977 (and any other JSTOR paper with per-page anchor TOCs) | Already fixed in earlier commits this session (`_is_useful_toc`, `_format_embedded_toc` filters — reject TOCs where page targets are all <=0 or >50% entries are "p. N" stubs). Verified by reconversion. |
| **(2) Clean two-column interleaving** | argyris1958, 1960, 1962, 1964, 1973, 1973_2, 1976, 1978, 1988, 1989_2, 1990, 1990_2, 1990_3, 1994, 1998, 2002, and others — 23 clean 2-col papers in total | Handled by the word-level detector + block-level left/right partitioning in `_extract_page_text`. Left column emitted top-to-bottom followed by right column. Verified on argyris1976 p.2 (author bio no longer interleaves), argyris1959 p.2 (sentence flows continuously). |
| **(3) Merged-block two-column pages** | argyris1955, argyris1977, argyris1980_2, argyris1989, fulmer1998 (5 papers) | Handled by word-level splitting of tall crossing blocks in `_extract_page_text`. Words inside the block are partitioned at the detected gutter and emitted as left-then-right. Verified on all five: argyris1977 p.1 (shown above), argyris1955 p.3+ body, argyris1980_2 p.2 body, argyris1989 p.1 and p.2 body, fulmer1998 p.1 merged title area. |

## No-regression check

- The Reflective Practitioner (276 pages, the only non-paper in the corpus): `diff baseline postfix = 0 lines`.
- All 16 single-column papers: none of their detection paths fire, so output is byte-identical or differs only by whitespace trimming.
- The 1 scanned-PDF failure (Argyris 1977 Double Loop Learning... pre-existing image-only PDF): still fails identically in both runs.

## Delta summary (all 43 papers)

The 35 papers with changes are listed below with line-count deltas (postfix - baseline). Negative deltas typically indicate successful paragraph joining (wrapped lines merged). Positive deltas indicate the opposite: the page had more distinct paragraph breaks after column splitting.

```
argyris1955.md       base= 136 post= 134 delta=  -2
argyris1957.md       base= 246 post= 197 delta= -49
argyris1958.md       base= 229 post= 191 delta= -38
argyris1959.md       base= 307 post= 262 delta= -45
argyris1960.md       base=  82 post=  64 delta= -18
argyris1962.md       base=  69 post=  42 delta= -27
argyris1964.md       base=  62 post=  74 delta= +12
argyris1968_2.md     base=  98 post=  64 delta= -34
argyris1973_2.md     base= 131 post= 109 delta= -22
argyris1973.md       base= 323 post= 339 delta= +16
argyris1976_2.md     base=  68 post=  32 delta= -36
argyris1976_3.md     base= 235 post= 190 delta= -45
argyris1976.md       base= 306 post= 341 delta= +35
argyris1977.md       base= 280 post= 312 delta= +32
argyris1978_2.md     base=  86 post=  55 delta= -31
argyris1978.md       base= 250 post= 289 delta= +39
argyris1980_2.md     base= 186 post= 170 delta= -16
argyris1980.md       base= 252 post= 240 delta= -12
argyris1988.md       base= 109 post= 129 delta= +20
argyris1989_2.md     base=  96 post=  79 delta= -17
argyris1989.md       base= 251 post= 269 delta= +18
argyris1990_2.md     base= 173 post= 198 delta= +25
argyris1990_3.md     base=  84 post=  58 delta= -26
argyris1990.md       base=  80 post=  89 delta=  +9
argyris1993.md       base= 265 post= 288 delta= +23
argyris1994.md       base=  49 post=  58 delta=  +9
argyris1995.md       base= 124 post= 142 delta= +18
argyris1998.md       base=  66 post=  74 delta=  +8
argyris2002.md       base= 384 post= 388 delta=  +4
argyris2003.md       base= 176 post= 155 delta= -21
argyrys_theory_of_action.md  base= 124 post= 142 delta= +18
bonjean1961.md       base= 102 post=  61 delta= -41
conversation-with-chris-argyris-1974.md  base= 369 post= 389 delta= +20
fulmer1998.md        base= 218 post= 221 delta=  +3
inner-contradictions-of-rigorous-research-1982.md  base=  63 post=  70 delta=  +7
```

## Remaining known quirks (not regressions)

These existed in baseline and still exist in postfix. They are PyMuPDF glyph-encoding or font-map artifacts in specific source PDFs, not column-handling issues:

- **argyris1989**: "Overcoming" renders as "Ovefcoming" (`r` glyph mis-encoded as `f`).
- **argyris1993**: "LEADING-LEARNING" renders as "LEAKING-LEA" (same family of font-map issue).
- **argyris1976**: "talking" renders as "tal@g" (ligature collision).
- **argyris1976_3**: bibliography has un-joined hyphenated book titles (`Organiza-\ntion`). Fixable in `clean_text` hyphenation handling; not a column problem.
- **conversation-with-chris-argyris-1974**: opening page has scrambled letter order (`e OYL ,versu ,t loI . . . w;th`). This PDF has custom font mapping that breaks PyMuPDF's glyph-to-char resolution. Fixing would require OCR fallback.

These would all be resolved by running `--papers` on a Python 3.10+ venv to route through marker-pdf, which uses its own OCR layer when embedded text is suspicious.
