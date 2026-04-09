# Quality-Gated OCR Auto-Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `convert_with_pymupdf` produces degraded text (low English dictionary-word ratio), detect it and auto-fall-back to OCR using the existing `auto_ocr` path.

**Architecture:** Add a module-level quality scorer that loads `/usr/share/dict/words` (with a small bundled fallback) and counts the fraction of sampled alphabetic tokens that appear in the wordlist. `convert_with_pymupdf` calls the scorer after writing output and raises `ConversionError` if the score is below a calibrated threshold. The existing `auto_ocr` trigger in `convert_pdf` is broadened to catch this new error so the retry path is reused.

**Tech Stack:** Python 3.7+, PyMuPDF (fitz), pytest (new dev dependency), `/usr/share/dict/words` (BSD/macOS/Linux system wordlist)

**Related docs:** `docs/quality-fallback-design.md`, issue AndySparks/book-convert#17

---

## Task 1: Add test infrastructure

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`
- Modify: `README.md` (new "Running tests" section) — deferred to Task 7

- [ ] **Step 1: Create requirements-dev.txt**

```
# Development / test dependencies
-r requirements.txt
pytest>=7.0
```

- [ ] **Step 2: Create empty tests/__init__.py**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 3: Create tests/conftest.py to make convert.py importable**

Create `tests/conftest.py`:

```python
"""Pytest conftest: add repo root to sys.path so tests can import convert.py."""
import sys
from pathlib import Path

# tests/conftest.py -> repo root is the parent directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

- [ ] **Step 4: Create a smoke test so we can verify pytest runs**

Create `tests/test_smoke.py`:

```python
"""Smoke test to verify pytest is wired up."""
import convert  # noqa: F401  — verifies conftest.py path setup


def test_smoke():
    assert 1 + 1 == 2


def test_convert_imports():
    """convert.py imports cleanly from the test environment."""
    assert hasattr(convert, "convert_pdf")
```

- [ ] **Step 5: Install pytest into the venv**

```bash
source .venv/bin/activate && pip install -r requirements-dev.txt
```

Expected: `Successfully installed pytest-X.Y.Z ...`

- [ ] **Step 6: Run pytest to verify it works**

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```

Expected: `test_smoke PASSED`, `test_convert_imports PASSED`, exit code 0.

- [ ] **Step 7: Commit**

```bash
git add requirements-dev.txt tests/__init__.py tests/conftest.py tests/test_smoke.py
git commit -m "$(cat <<'EOF'
Add pytest test infrastructure

First test infra in this repo. requirements-dev.txt pulls in pytest;
tests/ directory holds the suite with a conftest.py that puts the
repo root on sys.path so test files can import convert.py directly.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: English wordlist loader (TDD)

**Files:**
- Create: `tests/test_quality.py`
- Modify: `convert.py` (add `_load_english_wordlist` and `_FALLBACK_WORDLIST` near top of file, after line 152 where `MIN_TEXT_RATIO` is defined)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quality.py`:

```python
"""Tests for the text quality scoring module."""
import convert


def test_wordlist_loads_common_words():
    """The loader returns a frozenset containing common English words."""
    words = convert._load_english_wordlist()
    assert isinstance(words, frozenset)
    assert "the" in words
    assert "management" in words
    assert "organization" in words


def test_wordlist_is_lowercase():
    """All wordlist entries are lowercased."""
    words = convert._load_english_wordlist()
    # Sample 100 words and verify none have uppercase
    sample = list(words)[:100]
    for w in sample:
        assert w == w.lower(), f"Found non-lowercase word: {w!r}"


def test_wordlist_fallback_when_system_missing(monkeypatch, tmp_path):
    """When /usr/share/dict/words is missing, loader uses bundled fallback."""
    # Force the loader to think the system wordlist is missing by pointing
    # it at a nonexistent path.
    fake_path = tmp_path / "definitely-not-here"
    monkeypatch.setattr(convert, "_SYSTEM_WORDLIST_PATH", str(fake_path))
    # Clear the module-level cache so we re-invoke the loader logic.
    monkeypatch.setattr(convert, "_CACHED_WORDLIST", None)
    words = convert._load_english_wordlist()
    assert isinstance(words, frozenset)
    # Fallback must at least contain the most basic words.
    assert "the" in words
    assert "and" in words
    assert len(words) >= 100  # fallback is ~500 words; never zero
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_quality.py -v
```

Expected: All three tests FAIL with `AttributeError: module 'convert' has no attribute '_load_english_wordlist'` (or similar).

- [ ] **Step 3: Implement the loader**

In `convert.py`, add this block immediately after the existing `MIN_TEXT_RATIO = 0.1` line (around line 152):

```python
# --- Text quality scoring ---
# Path to the system English wordlist. Overridable in tests.
_SYSTEM_WORDLIST_PATH = "/usr/share/dict/words"

# Cached wordlist, populated on first call to _load_english_wordlist.
_CACHED_WORDLIST = None

# Bundled fallback wordlist for systems without /usr/share/dict/words.
# ~500 of the most common English words plus management/business vocabulary
# this tool's target corpus tends to contain.
_FALLBACK_WORDLIST = frozenset((
    # Top ~300 most common English words
    "the be to of and a in that have i it for not on with he as you do at "
    "this but his by from they we say her she or an will my one all would "
    "there their what so up out if about who get which go me when make can "
    "like time no just him know take people into year your good some could "
    "them see other than then now look only come its over think also back "
    "after use two how our work first well way even new want because any "
    "these give day most us is are was were been being am has had does did "
    "done being doing having should shall may might must could would will "
    "where why through between before under over between against during "
    "without within around above below across behind beyond beside beneath "
    "toward upon among along throughout despite regarding concerning "
    "very much many little few more less least best worse worst better "
    "another same different several such each every either neither both "
    "while whereas although though however therefore thus hence moreover "
    "furthermore nevertheless accordingly consequently otherwise likewise "
    "here there everywhere somewhere anywhere nowhere whenever wherever "
    # Management / business vocabulary
    "management manager managers managing leadership leader leaders "
    "organization organizations organizational company companies corporate "
    "business strategy strategic tactical operations operational executive "
    "executives decision decisions process processes system systems "
    "project projects product products quality productivity performance "
    "team teams group groups people person employee employees worker "
    "workers customer customers client clients market markets marketing "
    "sales revenue profit profits growth change innovation development "
    "analysis research study studies report reports meeting meetings "
    "communication communications culture values principles practice "
    "practices behavior behaviors theory theories model models framework "
    "frameworks method methods approach approaches technique techniques "
    "training development skill skills knowledge learning education "
    "experience expertise authority responsibility accountability "
    "delegation empowerment motivation engagement commitment "
    # Common book / text vocabulary
    "book books chapter chapters section sections page pages part parts "
    "introduction conclusion summary example examples figure figures "
    "table tables appendix index bibliography reference references "
    "author authors editor editors publisher publishers edition editions "
    "preface foreword acknowledgment acknowledgments contents "
    # Narrative / explanatory verbs
    "said says stated states explains explained describes described "
    "shows showed suggests suggested argues argued believes believed "
    "found finds discovered reveals revealed demonstrates demonstrated "
    "considers considered examines examined discusses discussed "
    "proposes proposed concludes concluded observes observed notes noted"
).split())


def _load_english_wordlist():
    """Return a frozenset of lowercased English words for quality scoring.

    Tries /usr/share/dict/words first (available on macOS and most Linux
    systems via BSD games or similar packages). Falls back to a bundled
    small wordlist if unavailable. Result is cached after first call.
    """
    global _CACHED_WORDLIST
    if _CACHED_WORDLIST is not None:
        return _CACHED_WORDLIST

    try:
        with open(_SYSTEM_WORDLIST_PATH, "r", encoding="utf-8", errors="replace") as f:
            words = {
                line.strip().lower()
                for line in f
                if line.strip().isalpha() and len(line.strip()) >= 2
            }
        if words:
            log.debug("Loaded %d words from %s", len(words), _SYSTEM_WORDLIST_PATH)
            _CACHED_WORDLIST = frozenset(words)
            return _CACHED_WORDLIST
    except (FileNotFoundError, PermissionError, OSError) as e:
        log.debug("Could not load system wordlist: %s", e)

    log.debug("Using bundled fallback wordlist (%d words)", len(_FALLBACK_WORDLIST))
    _CACHED_WORDLIST = _FALLBACK_WORDLIST
    return _CACHED_WORDLIST
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_quality.py -v
```

Expected: All three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add convert.py tests/test_quality.py
git commit -m "$(cat <<'EOF'
Add English wordlist loader for quality scoring

Loads /usr/share/dict/words when available, falls back to a bundled
~500-word frozenset covering common English plus management/business
vocabulary. Cached on first call. Groundwork for the quality scorer
that gates pymupdf extractions.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Text quality scorer (TDD)

**Files:**
- Modify: `tests/test_quality.py` (append new tests)
- Modify: `convert.py` (add `_text_quality_score` after the wordlist loader)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quality.py`:

```python
# --- Quality scorer tests ---

CLEAN_ENGLISH = """
The organization's leadership must consider the behavior of employees
across every department. A manager who understands the people on the
team can build trust through clear communication. Performance improves
when workers feel their contributions are recognized and their ideas
are taken seriously by the executives. This principle appears in every
major study of management practice over the past fifty years, from the
earliest research on motivation to contemporary work on psychological
safety and team effectiveness. Organizations that ignore it pay a cost
in turnover, engagement, and productivity.
""" * 3  # Repeat to ensure >=100 tokens


MANGLED_TEXT = """
The organi7ation's leadersh1p n1ust consider the behavi0r of en1ployees
acrr)ss every departn1ent. A n1anager vvho understands the peop1e on the
tean1 can bui1d trvst through c1ear cornn1unication. Perforn1ance in1prrwes
vvhen vvorkers fee1 their contributirms are recogni7ed and their ideas
are tekert seriou$ly by the executi\/es. This princip1e appears in every
n1ajor study of managen1ent practice ()ver the past fifty years, from the
ear1iest research on n1otivation to conten1porary vvork on psycho1ogica1
safety and tean1 effectivenes$. Organi7ations that ignore it pay a cost
in turn()ver, engagen1ent, and productivity.
""" * 3


def test_quality_clean_english_scores_high():
    """A clean English paragraph scores >= 0.7."""
    score = convert._text_quality_score(CLEAN_ENGLISH)
    assert score >= 0.7, f"Expected >=0.7 for clean English, got {score:.3f}"


def test_quality_mangled_text_scores_low():
    """A mangled paragraph (ligature artifacts) scores < 0.5."""
    score = convert._text_quality_score(MANGLED_TEXT)
    assert score < 0.5, f"Expected <0.5 for mangled text, got {score:.3f}"


def test_quality_short_text_returns_one():
    """Text with fewer than 100 usable tokens returns exactly 1.0."""
    # "the" x 50: 50 tokens total, below the 100 threshold
    short = "the " * 50
    score = convert._text_quality_score(short)
    assert score == 1.0, f"Expected 1.0 for short text, got {score}"


def test_quality_strips_markdown():
    """Markdown syntax characters don't pollute the score."""
    markdown = "# Heading\n\n" + CLEAN_ENGLISH + "\n\n* bullet\n* another\n"
    score = convert._text_quality_score(markdown)
    assert score >= 0.7, f"Markdown should not drag score down, got {score:.3f}"


def test_quality_strips_trailing_punctuation():
    """Words with trailing punctuation (word., word,) are still counted."""
    text = ("organization, management, leadership, business, strategy, "
            "performance, team, people, process, system. " * 15)
    score = convert._text_quality_score(text)
    # Every token after stripping punctuation is a real word → ~1.0
    assert score >= 0.9, f"Expected >=0.9 for punctuated real words, got {score:.3f}"


def test_quality_strips_page_markers():
    """HTML page markers (<!-- Page N -->) don't contribute tokens."""
    text = "<!-- Page 1 -->\n\n" + CLEAN_ENGLISH
    score = convert._text_quality_score(text)
    assert score >= 0.7
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_quality.py -v
```

Expected: The 6 new tests FAIL with `AttributeError: module 'convert' has no attribute '_text_quality_score'`. Wordlist tests should still PASS.

- [ ] **Step 3: Implement the scorer**

In `convert.py`, add this immediately after the `_load_english_wordlist` function:

```python
# Regex for stripping markdown syntax before tokenization.
# We strip: HTML comments (<!-- ... -->), headings/bullets/emphasis markers,
# table pipes, backticks, and horizontal rules.
_MARKDOWN_STRIP_RE = re.compile(
    r'<!--.*?-->|[#*_`|]+|^-{3,}$',
    re.MULTILINE | re.DOTALL
)

# Punctuation to strip from the start/end of tokens before wordlist lookup.
_TOKEN_PUNCT = '.,;:!?"\'()[]{}<>—–-'


def _text_quality_score(text, sample_size=2000):
    """Return a 0.0-1.0 quality score for extracted text.

    Higher is better. Computed as the fraction of sampled alphabetic tokens
    (length >= 3) that appear in the English wordlist. Returns 1.0 when
    there are too few tokens to judge (< 100), to avoid flagging short or
    image-heavy docs.

    The scorer is deterministic: it always samples the first `sample_size`
    qualifying tokens, so runs are reproducible for debugging.
    """
    # Strip markdown syntax so it doesn't contribute garbage tokens.
    cleaned = _MARKDOWN_STRIP_RE.sub(' ', text)

    # Tokenize, strip trailing punctuation, keep only pure alphabetic
    # tokens of length >= 3.
    tokens = []
    for raw in cleaned.split():
        stripped = raw.strip(_TOKEN_PUNCT)
        if len(stripped) >= 3 and stripped.isalpha():
            tokens.append(stripped.lower())

    # Too little text to judge — refuse to flag.
    if len(tokens) < 100:
        return 1.0

    sampled = tokens[:sample_size]
    wordlist = _load_english_wordlist()
    matches = sum(1 for t in sampled if t in wordlist)
    return matches / len(sampled)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_quality.py -v
```

Expected: All 9 tests PASS (3 from Task 2 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add convert.py tests/test_quality.py
git commit -m "$(cat <<'EOF'
Add _text_quality_score for detecting degraded extractions

Computes fraction of sampled alphabetic tokens that appear in the
English wordlist. Strips markdown syntax, trims punctuation, filters
to tokens of length >= 3. Returns 1.0 for short text to avoid flagging
pamphlets or image-heavy docs. Deterministic (first-N sampling) so
runs are reproducible.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Calibrate QUALITY_THRESHOLD against real outputs

**Files:**
- None modified in this task — this is a measurement step that informs Task 5's constant.

- [ ] **Step 1: Score the three existing outputs**

Run this one-off from the repo root:

```bash
source .venv/bin/activate && python -c "
import convert
for path in [
    'output/Management/The Human Side of Enterprise, Annotated Edition.md',
    'output/Management/The-Functions-Of-The-Executive.md',
    'output/The Pyramid Principle.md',
]:
    with open(path) as f:
        text = f.read()
    score = convert._text_quality_score(text)
    print(f'{score:.3f}  {path}')
"
```

Expected output shape (numbers will vary):

```
0.8XX  output/Management/The Human Side of Enterprise, Annotated Edition.md
0.7XX  output/Management/The-Functions-Of-The-Executive.md
0.3XX  output/The Pyramid Principle.md
```

- [ ] **Step 2: Record the numbers and pick a threshold**

Write the three scores down as e.g.:

```
HUMAN_SIDE = 0.xxx
FUNCTIONS  = 0.xxx
PYRAMID    = 0.xxx
```

Pick a threshold T such that:
- `T > PYRAMID + 0.15`
- `T < min(HUMAN_SIDE, FUNCTIONS) - 0.15`

If no such T exists (the gap is < 0.30), **STOP and escalate to the user**: the scorer needs to be rethought. Paste the numbers and ask before proceeding.

Record the chosen threshold; it goes into Task 5.

- [ ] **Step 3: No commit** (measurement only — numbers will be committed as a comment in Task 5)

---

## Task 5: Wire quality check into convert_with_pymupdf

**Files:**
- Modify: `convert.py` — add `QUALITY_THRESHOLD` constant; add check inside `convert_with_pymupdf` after the writing loop; broaden `auto_ocr` trigger in `convert_pdf`.

- [ ] **Step 1: Add the QUALITY_THRESHOLD constant**

In `convert.py`, immediately after the existing `MIN_TEXT_RATIO = 0.1` line (around line 152), add:

```python
# Minimum English-dictionary-word ratio for a pymupdf extraction to be
# accepted without falling back to OCR. Calibrated against:
#   The Human Side of Enterprise (good pymupdf):   X.XXX
#   The Functions of the Executive (good OCR):     X.XXX
#   The Pyramid Principle (bad pymupdf, mangled):  X.XXX
# Set with a >=0.15 margin on each side of the gap. See
# docs/quality-fallback-design.md for the rationale.
QUALITY_THRESHOLD = 0.XX  # <-- Replace with the value chosen in Task 4
```

Replace the `X.XXX` placeholders in the comment with the actual calibration numbers from Task 4, and the `0.XX` with the chosen threshold.

- [ ] **Step 2: Add quality check inside convert_with_pymupdf**

In `convert.py`, find the section of `convert_with_pymupdf` that currently looks like this (around lines 1332-1343):

```python
    if skipped_toc_pages:
        print(f"  Replaced {skipped_toc_pages} broken TOC page(s) with embedded bookmark TOC")

    # Check if we got enough text to consider this a real conversion
    if total_pages > 0 and (pages_with_text / total_pages) < MIN_TEXT_RATIO:
        output_file.unlink(missing_ok=True)
        raise ConversionError(
            f"Only {pages_with_text}/{total_pages} pages had extractable text. "
            f"This PDF may be scanned. Try: --method ocr"
        )

    print(f"  -> {output_file}")
```

Insert a new quality check between the existing `MIN_TEXT_RATIO` check and the `print(f"  -> {output_file}")` line. The full replacement is:

```python
    if skipped_toc_pages:
        print(f"  Replaced {skipped_toc_pages} broken TOC page(s) with embedded bookmark TOC")

    # Check if we got enough text to consider this a real conversion
    if total_pages > 0 and (pages_with_text / total_pages) < MIN_TEXT_RATIO:
        output_file.unlink(missing_ok=True)
        raise ConversionError(
            f"Only {pages_with_text}/{total_pages} pages had extractable text. "
            f"This PDF may be scanned. Try: --method ocr"
        )

    # Check text quality: catches PDFs with non-standard font encodings that
    # produce extractable-but-garbled output (e.g. "n1ethod" for "method").
    # When quality is low we raise a ConversionError the caller can catch
    # and route to OCR via the auto_ocr fallback.
    extracted = output_file.read_text(encoding="utf-8", errors="replace")
    quality = _text_quality_score(extracted)
    log.debug("Text quality score: %.3f", quality)
    if quality < QUALITY_THRESHOLD:
        output_file.unlink(missing_ok=True)
        raise ConversionError(
            f"Low quality text extraction (score: {quality:.2f}, "
            f"threshold: {QUALITY_THRESHOLD:.2f}). This PDF may have "
            f"non-standard font encoding. Try: --method ocr"
        )

    print(f"  -> {output_file}")
```

- [ ] **Step 3: Broaden the auto_ocr trigger in convert_pdf**

In `convert.py`, find this block in `convert_pdf` (around lines 1504-1512):

```python
    except ConversionError as e:
        if auto_ocr and method != "ocr" and "scanned" in str(e).lower():
            print(f"  Text extraction failed, auto-retrying with OCR...")
            try:
                check_dependencies("ocr")
                return convert_with_ocr(pdf_path, output_dir)
            except DependencyError as dep_e:
                print(f"  OCR fallback unavailable: {dep_e}")
                return False
```

Replace with:

```python
    except ConversionError as e:
        error_msg = str(e).lower()
        auto_ocr_triggers = ("scanned", "low quality")
        if auto_ocr and method != "ocr" and any(t in error_msg for t in auto_ocr_triggers):
            print(f"  Text extraction failed, auto-retrying with OCR...")
            try:
                check_dependencies("ocr")
                return convert_with_ocr(pdf_path, output_dir)
            except DependencyError as dep_e:
                print(f"  OCR fallback unavailable: {dep_e}")
                return False
```

- [ ] **Step 4: Run existing tests to verify nothing regressed**

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```

Expected: All 9 quality tests PASS, smoke test PASSES, exit 0.

- [ ] **Step 5: Commit**

```bash
git add convert.py
git commit -m "$(cat <<'EOF'
Auto-fallback to OCR when pymupdf extraction quality is low

Adds a QUALITY_THRESHOLD-gated check to convert_with_pymupdf: after
writing the output file, score its English dictionary-word ratio and
raise ConversionError('low quality...') if below threshold. Broadens
the auto_ocr trigger in convert_pdf to catch this new error alongside
the existing 'scanned' match, so degraded extractions (e.g. PDFs with
non-standard font encodings like The Pyramid Principle) now route to
OCR automatically instead of silently shipping garbled output.

Fixes AndySparks/book-convert#17

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: End-to-end verification against the real Pyramid Principle PDF

**Files:**
- None modified. This is a manual verification step.

- [ ] **Step 1: Move the Pyramid Principle back to input/**

The earlier batch run archived the PDFs with timestamps. Find the archived file and restore it:

```bash
ls archive/ | grep -i pyramid
```

Copy (do not move — leave the archive intact) the matching file back to `input/` under its original name:

```bash
cp "archive/<the-found-file>" "input/The Pyramid Principle.pdf"
```

- [ ] **Step 2: Delete any previous Pyramid Principle output**

```bash
rm -f "output/The Pyramid Principle.md"
```

- [ ] **Step 3: Run the default conversion (pymupdf with auto_ocr)**

```bash
source .venv/bin/activate && python convert.py "input/The Pyramid Principle.pdf"
```

Expected console output (approximate):

```
Converting with PyMuPDF: The Pyramid Principle.pdf
  278 pages
  Processed 50/278 pages...
  ...
  FAILED: Low quality text extraction (score: 0.XX, threshold: 0.XX). ...
  Text extraction failed, auto-retrying with OCR...
Converting with OCR: The Pyramid Principle.pdf
  278 pages
  ...
  -> output/The Pyramid Principle.md
```

**What to check:**
- The quality check fires (`Low quality text extraction` in output)
- The auto_ocr path triggers (`auto-retrying with OCR`)
- A final `output/The Pyramid Principle.md` file exists and is the OCR version

- [ ] **Step 4: Score the new output to confirm it passes the gate**

```bash
source .venv/bin/activate && python -c "
import convert
with open('output/The Pyramid Principle.md') as f:
    text = f.read()
print(f'New score: {convert._text_quality_score(text):.3f}')
print(f'Threshold: {convert.QUALITY_THRESHOLD:.3f}')
"
```

Expected: new score is comfortably above `QUALITY_THRESHOLD`. If not, the OCR output is also degraded and the threshold needs reconsideration — escalate.

- [ ] **Step 5: Spot-check the new file for readability**

Read the first ~80 lines and a middle chunk. Confirm: no `vv`/`tn`/`n1` mangling, body text coherent, page markers present. Use the Read tool.

- [ ] **Step 6: Verify good files still convert cleanly (regression check)**

Restore one known-good PDF from archive and re-run:

```bash
ls archive/ | grep -i "human side"
cp "archive/<the-found-file>" "input/The Human Side of Enterprise, Annotated Edition.pdf"
rm -f "output/Management/The Human Side of Enterprise, Annotated Edition.md" \
      "output/The Human Side of Enterprise, Annotated Edition.md"
source .venv/bin/activate && python convert.py "input/The Human Side of Enterprise, Annotated Edition.pdf"
```

Expected: converts via pymupdf, does NOT trigger auto_ocr. Output includes `-> output/The Human Side of Enterprise, Annotated Edition.md` (or similar) with no "Low quality" or "auto-retrying" messages.

- [ ] **Step 7: Clean up input/ directory**

```bash
rm -f "input/The Pyramid Principle.pdf" \
      "input/The Human Side of Enterprise, Annotated Edition.pdf"
```

The archived copies remain in place for future reference.

- [ ] **Step 8: No commit** (verification only)

---

## Task 7: Update README with test instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Running tests" section to README.md**

In `README.md`, find the existing `## Tips` section. Immediately **before** it, insert a new section:

```markdown
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
```

- [ ] **Step 2: Update the Tips section to mention auto-fallback**

In `README.md`, find this bullet in the Tips section:

```markdown
- **Use `--ocr` only if** the default mode produces empty or garbled output -- this usually means the PDF is scanned/image-based. The tool will detect this and suggest OCR automatically.
```

Replace with:

```markdown
- **Use `--ocr` only if** the default mode produces empty or garbled output -- this usually means the PDF is scanned/image-based. The tool automatically detects both fully-scanned PDFs and PDFs with non-standard font encodings that produce garbled text, and falls back to OCR in both cases.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
Document pytest setup and quality-gated OCR fallback

Adds a "Running tests" section pointing at requirements-dev.txt and
tests/, and updates the OCR tip to reflect that the tool now catches
degraded extractions (not just fully-scanned PDFs) and auto-falls-back
to OCR in both cases.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Close the loop on the GitHub issue

**Files:** none.

- [ ] **Step 1: Push the branch and verify CI (if any) passes**

```bash
git push
```

If the repo has CI configured (check `.github/workflows/`), wait for it to go green. If there's no CI, skip.

- [ ] **Step 2: Close issue #17 with a reference to the fix commit**

```bash
gh issue close 17 --repo AndySparks/book-convert --comment "Fixed by the quality-gated OCR auto-fallback. See commit message on main for details; design doc at docs/quality-fallback-design.md."
```

- [ ] **Step 3: Announce completion to the user**

Report: tests passing, Pyramid Principle now auto-falls-back and produces a clean output, Human Side still converts via pymupdf without the fallback, issue closed.

---

## Summary of files touched

| File | Change | Task |
|---|---|---|
| `requirements-dev.txt` | New | 1 |
| `tests/__init__.py` | New | 1 |
| `tests/test_smoke.py` | New | 1 |
| `tests/test_quality.py` | New, extended | 2, 3 |
| `convert.py` | Add loader + scorer + QUALITY_THRESHOLD + hook into convert_with_pymupdf + broaden auto_ocr trigger | 2, 3, 5 |
| `README.md` | Add test section, update OCR tip | 7 |

No changes to `requirements.txt`, `CLAUDE.md`, or the existing source PDFs / outputs.
