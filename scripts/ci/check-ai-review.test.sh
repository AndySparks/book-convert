#!/usr/bin/env bash
# check-ai-review.test.sh — verification-gate-symmetry for the AI-review
# gate predicate: RED on a PR-shaped diff+body missing the section (and on
# "rounds: 1"), GREEN on a compliant body AND on an exempt docs-only PR.
set -euo pipefail
GUARD="$(cd "$(dirname "$0")" && pwd)/check-ai-review.sh"

fail() { echo "FAIL: $*"; exit 1; }

COMPLIANT_BODY='Fixes the folio probe.

## AI review — rounds: 2, engine: codex, verdict: pass

Round 1 found 3 actionables; round 2 verified the fixes.'

# 1. RED: mixed diff (code + docs), body with no AI-review section -> exit 1,
#    message names the required format and the ruling.
set +e
out=$(printf '%s\n' "convert.py" "docs/notes.md" \
  | PR_BODY='Just a quick fix.' "$GUARD" 2>&1)
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "missing section exited $rc, want 1"
printf '%s\n' "$out" | grep -q '## AI review' || fail "required format not quoted; got: $out"
printf '%s\n' "$out" | grep -q '9.2' || fail "ruling not named; got: $out"
echo "ok 1 - non-docs diff without section fails, quoting format + ruling"

# 2. GREEN: same diff, compliant body -> pass
printf '%s\n' "convert.py" \
  | PR_BODY="$COMPLIANT_BODY" "$GUARD" >/dev/null || fail "compliant body refused"
echo "ok 2 - non-docs diff with compliant section passes"

# 3. GREEN: docs-only diff (*.md anywhere + anything under docs/), no section
printf '%s\n' "docs/notes.md" "docs/notes.txt" "README.md" \
  | PR_BODY='No review here.' "$GUARD" >/dev/null || fail "docs-only diff refused"
echo "ok 3 - docs-only diff without section is exempt"

# 4. RED: one code file among docs revokes the exemption
set +e
printf '%s\n' "README.md" "report.py" \
  | PR_BODY='No review here.' "$GUARD" >/dev/null 2>&1 && fail "mixed diff passed"
set -e
echo "ok 4 - mixed diff without section fails"

# 5. RED: "rounds: 1" is not "rounds: 2"; nor is "rounds: 12"
for bad in \
  '## AI review — rounds: 1, engine: codex, verdict: pass' \
  '## AI review — rounds: 12, engine: codex, verdict: pass'; do
  set +e
  printf 'report.py\n' | PR_BODY="$bad" "$GUARD" >/dev/null 2>&1 \
    && fail "wrong round count passed: $bad"
  set -e
done
echo "ok 5 - rounds: 1 / rounds: 12 fail"

# 6. RED: section + rounds present but no verdict word
set +e
printf 'report.py\n' \
  | PR_BODY='## AI review — rounds: 2, engine: codex' "$GUARD" >/dev/null 2>&1 \
  && fail "verdict-less body passed"
set -e
echo "ok 6 - section without a verdict fails"

# 7. GREEN: lenient formatting — lowercase heading, colon-less punctuation
printf 'report.py\n' \
  | PR_BODY='## ai review
rounds: 2 (codex round 1 found, round 2 verified)
verdict: pass' "$GUARD" >/dev/null || fail "leniently-formatted body refused"
echo "ok 7 - lenient formatting still passes"

# 8. GREEN: empty diff passes
printf '' | PR_BODY='' "$GUARD" >/dev/null || fail "empty diff refused"
echo "ok 8 - empty diff passes"

echo "PASS check-ai-review"
