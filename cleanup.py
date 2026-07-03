"""Post-conversion markdown cleanup — repair common PDF-extraction artifacts.

PDF text extraction (all backends) leaves a recurring set of cosmetic
artifacts that no backend fixes on its own:

  * Dropped-space joins where a function word is glued to its neighbour
    ("thefrozen" -> "the frozen", "sucha" -> "such a"). The joined form is
    never a legitimate English word, so splitting *restores* the author's
    original text rather than altering it.
  * Stray-consonant citation ghosts, where a lone letter is glued to a
    capitalised name after an attribution dash ("—wWilliam" -> "—William").
  * "Picture text" blocks emitted by pymupdf4llm: some hold the real Table
    of Contents rendered as a table (keep, unwrapped), others hold pure OCR
    garble like ISBN barcodes (drop).

This module encodes the *safe* subset of those repairs. The guiding rule is
verbatim fidelity: never mangle a real word. In particular the de-join pass
must not split legitimate single words that a spellchecker happens not to
know — British spellings (colour, humour), coinages (moocow, givenness),
proper nouns, or Latin (africanus). It stays safe by only splitting at a
*whitelisted function-word* boundary, and only when the whole token is not a
known word. Traps like "aeroplane" or "manservants" have no function-word
split point at all, so the rule never touches them; the residual short-func
troublemakers ("attaches" -> "at taches") are excluded by whitelisting only
unambiguous leading function words.

The de-join pass needs a dictionary (pyspellchecker). If it is not installed
the pass degrades gracefully: the dictionary-free repairs (picture-text,
stray consonants) still run, and `stats["dejoin_available"]` is False so the
caller can surface a hint.

Public API:
    clean_markdown(text) -> (cleaned_text, stats)
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, Optional, Tuple

# --- function-word vocabulary ------------------------------------------------

# Words that can anchor a split (at least one half of a join must be one).
STRICT_FUNC = {
    'the', 'a', 'an', 'of', 'and', 'or', 'to', 'in', 'on', 'at', 'for', 'from',
    'with', 'was', 'were', 'is', 'are', 'be', 'been', 'being', 'his', 'her',
    'its', 'their', 'our', 'my', 'so', 'as', 'by', 'not', 'but', 'that', 'this',
    'these', 'those', 'would', 'could', 'should', 'had', 'has', 'have', 'out',
    'off', 'over', 'into', 'upon', 'such', 'more', 'very', 'all', 'one', 'two',
    'no', 'we', 'he', 'she', 'him', 'them', 'then', 'than', 'up', 'if', 'it',
    'do', 'who', 'when', 'where', 'which',
}

# Function words safe as the *leading* half of a join. Short two-letter words
# that frequently begin real English words (at->attaches, as->assay,
# off->offate, be->become) are deliberately excluded to avoid false splits.
SAFE_LEADING = {
    'the', 'and', 'of', 'to', 'in', 'on', 'by', 'for', 'from', 'with', 'was',
    'were', 'are', 'is', 'has', 'had', 'have', 'out', 'over', 'into', 'upon',
    'such', 'that', 'this', 'these', 'those', 'more', 'very', 'all', 'one',
    'two', 'our', 'her', 'his', 'its', 'their', 'been', 'being', 'would',
    'could', 'should', 'than', 'then', 'when', 'where', 'which', 'who', 'not',
    'but',
}

# A trailing function-word half is allowed for any STRICT_FUNC word except
# these — British -our / Latin -us endings that would masquerade as "our"/"us"
# splits (colour -> "col our", genus -> "gen us"). Trailing joins are far
# safer than leading ones: real words that end in a function word are almost
# always dictionary-known (format, carton, maybe) and so are filtered by the
# whole-token-known check before a split is ever attempted.
_BAD_TRAILING = {'our', 'ours', 'us'}


# --- dictionary (optional) ---------------------------------------------------

@lru_cache(maxsize=1)
def _speller():
    """Return a SpellChecker instance, or None if pyspellchecker is absent."""
    try:
        from spellchecker import SpellChecker
    except Exception:
        return None
    return SpellChecker(distance=1)


def _known(word: str, sp) -> bool:
    return len(sp.known([word.lower()])) == 1


def _best_split(tok: str, sp) -> Optional[Tuple[str, str]]:
    """Return (left, right) if `tok` is a safe function-word join, else None.

    A split is valid when each half is a whitelisted function word or a known
    word of length >= 3, at least one half is a function word, and the
    function-word half is on its whitelisted side. The whole token must be
    unknown (so we never split a real word). Among valid splits, prefer the
    one with the longest shorter-half (most balanced, least fragmentary).
    """
    low = tok.lower()
    if _known(low, sp):
        return None
    best = None
    for i in range(1, len(low)):
        l, r = low[:i], low[i:]
        if r in _BAD_TRAILING:
            continue
        l_func, r_func = l in STRICT_FUNC, r in STRICT_FUNC
        l_ok = l_func or (len(l) >= 3 and _known(l, sp))
        r_ok = r_func or (len(r) >= 3 and _known(r, sp))
        if not (l_ok and r_ok and (l_func or r_func)):
            continue
        # A leading function-word half is only allowed from the whitelist
        # (blocks short-func false splits like "at"+"taches"). Trailing
        # function words are gated only by _BAD_TRAILING, handled above.
        if l_func and l not in SAFE_LEADING:
            continue
        # A trailing "a"/"an" swept onto a short content stem is the classic
        # way a proper noun gets mangled ("Iowa" -> "low a"). Require the stem
        # to be a function word or >= 4 chars; "have a"/"from a" still pass.
        if r in ('a', 'an') and not (l_func or len(l) >= 4):
            continue
        key = min(len(l), len(r))
        if best is None or key > best[0]:
            best = (key, l, r)
    return (best[1], best[2]) if best else None


def _dejoin(text: str, sp) -> Tuple[str, int]:
    """Split safe function-word joins. Returns (text, num_distinct_tokens)."""
    # Collect distinct all-lowercase candidate tokens first, resolve each once,
    # then apply as whole-word replacements. Because every fixed token is a
    # non-word, a global \b replacement can only ever hit the join itself.
    repl: Dict[str, str] = {}
    for m in re.finditer(r'\b[a-z]{4,}\b', text):
        tok = m.group(0)
        if tok in repl:
            continue
        s = _best_split(tok, sp)
        if s:
            repl[tok] = f'{s[0]} {s[1]}'
    for tok, rep in repl.items():
        text = re.sub(r'\b' + re.escape(tok) + r'\b', rep, text)
    return text, len(repl)


# --- stray-consonant citation ghosts ----------------------------------------

# A lone consonant (not the words "a"/"i") glued to a Capitalised word:
# "wWilliam" -> "William", "tThe" -> "The". Always an extraction artifact.
_STRAY = re.compile(r'\b([b-df-hj-np-tv-z])([A-Z][a-z]{2,})\b')


def _fix_stray_consonants(text: str) -> Tuple[str, int]:
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(2)

    return _STRAY.sub(sub, text), n[0]


# --- picture-text blocks -----------------------------------------------------

_PICTEXT = re.compile(
    r'\*\*-+ Start of picture text -+\*\*<br>\s*(.*?)\s*'
    r'\*\*-+ End of picture text -+\*\*<br>',
    re.DOTALL,
)


def _fix_picture_text(text: str) -> Tuple[str, int, int]:
    """Unwrap picture-text blocks that hold a real TOC table; drop garble."""
    kept = [0]
    dropped = [0]

    def sub(m):
        inner = m.group(1)
        # Heuristic: a genuine table of contents rendered as a markdown table.
        looks_like_toc = (
            'Index of Terms' in inner
            or (inner.count('|') >= 8 and re.search(r'(?i)\bcontents\b|\bchapter\b', inner))
        )
        if looks_like_toc:
            kept[0] += 1
            return inner
        dropped[0] += 1
        return ''

    text = _PICTEXT.sub(sub, text)
    return text, kept[0], dropped[0]


# --- public API --------------------------------------------------------------

def clean_markdown(text: str) -> Tuple[str, Dict]:
    """Repair common extraction artifacts. Idempotent and verbatim-safe.

    Returns (cleaned_text, stats) where stats records how many of each repair
    were applied. The de-join pass is skipped (0 joins, dejoin_available=False)
    when pyspellchecker is not installed.
    """
    stats: Dict = {
        'function_word_joins': 0,
        'stray_consonant_fixes': 0,
        'toc_blocks_unwrapped': 0,
        'garble_blocks_removed': 0,
        'dejoin_available': False,
    }

    sp = _speller()
    if sp is not None:
        stats['dejoin_available'] = True
        text, stats['function_word_joins'] = _dejoin(text, sp)

    text, stats['stray_consonant_fixes'] = _fix_stray_consonants(text)
    text, stats['toc_blocks_unwrapped'], stats['garble_blocks_removed'] = \
        _fix_picture_text(text)

    # Collapse any blank-line runs left by removed garble blocks.
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text, stats
