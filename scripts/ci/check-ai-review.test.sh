#!/usr/bin/env bash
# check-ai-review.test.sh — verification-gate-symmetry for the AI-review
# gate predicate: RED on a conversion-code diff+body missing the section,
# on wrong round counts (1, 12, 2+, 2.5), on a missing engine, and on a
# rename laundered into docs/; GREEN on a compliant body AND on an exempt
# docs-only PR.
set -euo pipefail
GUARD="$(cd "$(dirname "$0")" && pwd)/check-ai-review.sh"

fail() { echo "FAIL: $*"; exit 1; }

COMPLIANT_BODY='Fixes the folio probe.

## AI review — rounds: 2, engine: codex, verdict: pass

Round 1 found 3 actionables; round 2 verified the fixes.'

# 1. RED: convert.py diff, body with no AI-review section -> exit 1,
#    message names the required format and the ruling (codex round 1, P1:
#    conversion code is the gate's primary target here).
set +e
out=$(printf 'convert.py\n' | PR_BODY='Just a quick fix.' "$GUARD" 2>&1)
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "convert.py diff exited $rc, want 1"
printf '%s\n' "$out" | grep -q '## AI review' || fail "required format not quoted; got: $out"
printf '%s\n' "$out" | grep -q '9.2' || fail "ruling not named; got: $out"
echo "ok 1 - convert.py diff without section fails, quoting format + ruling"

# 2. RED: non-exempt paths, alone — nested .md outside docs/, non-md under
#    docs/, CLAUDE.md, code, corpus
for p in "scripts/fix_frontmatter.py" "tests/test_cleanup.py" \
         ".github/workflows/x.yml" "output/Management/book.md" \
         "8-DECISIONS/2026-01-01-x.md" "docs/notes.txt" "CLAUDE.md" \
         "requirements.txt"; do
  set +e
  printf '%s\n' "$p" | PR_BODY='No review.' "$GUARD" >/dev/null 2>&1 \
    && fail "non-exempt path '$p' passed as docs-only"
  set -e
done
echo "ok 2 - nested .md, docs/ non-md, CLAUDE.md, code + corpus paths never exempt"

# 3. GREEN: conversion-code diff, compliant body -> pass
printf 'convert.py\n' \
  | PR_BODY="$COMPLIANT_BODY" "$GUARD" >/dev/null || fail "compliant body refused"
echo "ok 3 - code diff with compliant section passes"

# 4. GREEN: docs-only diff (docs/**/*.md + root *.md), no section
printf '%s\n' "docs/notes.md" "docs/sub/guide.md" "README.md" "1-ROADMAP.md" \
  | PR_BODY='No review here.' "$GUARD" >/dev/null || fail "docs-only diff refused"
echo "ok 4 - docs-only diff without section is exempt"

# 5. RED: one code file among docs revokes the exemption
set +e
printf '%s\n' "README.md" "report.py" \
  | PR_BODY='No review here.' "$GUARD" >/dev/null 2>&1 && fail "mixed diff passed"
set -e
echo "ok 5 - mixed diff without section fails"

# 6. RED: wrong round counts — 1, 12, 2+, 2.5 (codex round 1, P2)
for bad in \
  '## AI review — rounds: 1, engine: codex, verdict: pass' \
  '## AI review — rounds: 12, engine: codex, verdict: pass' \
  '## AI review — rounds: 2+, engine: codex, verdict: pass' \
  '## AI review — rounds: 2.5, engine: codex, verdict: pass'; do
  set +e
  printf 'convert.py\n' | PR_BODY="$bad" "$GUARD" >/dev/null 2>&1 \
    && fail "wrong round count passed: $bad"
  set -e
done
echo "ok 6 - rounds: 1 / 12 / 2+ / 2.5 all fail"

# 7. RED: no engine named — the record can't support the spot audit
#    (codex round 1, P1)
set +e
printf 'convert.py\n' \
  | PR_BODY='## AI review — rounds: 2, verdict: pass' "$GUARD" >/dev/null 2>&1 \
  && fail "engine-less body passed"
set -e
echo "ok 7 - section without an engine fails"

# 8. RED: section + rounds + engine present but no verdict word
set +e
printf 'convert.py\n' \
  | PR_BODY='## AI review — rounds: 2, engine: codex' "$GUARD" >/dev/null 2>&1 \
  && fail "verdict-less body passed"
set -e
echo "ok 8 - section without a verdict fails"

# 9. RED: rename laundering — report.py renamed to docs/report.md; the
#    workflow feeds BOTH sides, and the old side must revoke the exemption
#    (codex round 1, P2)
set +e
printf '%s\n' "docs/report.md" "report.py" \
  | PR_BODY='No review.' "$GUARD" >/dev/null 2>&1 && fail "rename into docs/ passed"
set -e
echo "ok 9 - rename old-side path (report.py -> docs/report.md) revokes exemption"

# 10. GREEN: lenient formatting — lowercase heading, fields on separate lines
printf 'convert.py\n' \
  | PR_BODY='## ai review
rounds: 2 (codex round 1 found, round 2 verified)
engine: codex
verdict: pass' "$GUARD" >/dev/null || fail "leniently-formatted body refused"
echo "ok 10 - lenient formatting still passes"

# 11. GREEN: empty diff passes
printf '' | PR_BODY='' "$GUARD" >/dev/null || fail "empty diff refused"
echo "ok 11 - empty diff passes"

echo "PASS check-ai-review"
