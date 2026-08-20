#!/usr/bin/env bash
# check-ai-review.sh — the different-model review-gate predicate
# (wiki-reliability Phase 4.2, ruling § 9.2: management-craft
# docs/2B-PROJECTS/wiki-reliability/v1/RESEARCH.md; written rule at
# ~/.claude/CLAUDE.md § "Different-model review gate").
#
# PRs that touch anything beyond docs get a different-model review —
# exactly two rounds — recorded in the PR body as an `## AI review`
# section. This script is the whole predicate; the workflow
# (.github/workflows/ai-review-gate.yml) only feeds it.
#
# Input:  changed file paths on stdin, one per line (the workflow feeds it
#         the pulls/N/files listing); the PR body in $PR_BODY.
# Exempt: when EVERY changed path is a *.md file or under docs/.
# Pass:   otherwise, when the body contains an `## AI review` heading,
#         "rounds: 2" (exactly 2 — "rounds: 1" fails), and a verdict.
#         Lenient on formatting, strict on those three facts.
# Exit 0 pass / 1 fail.
#
# Standalone on purpose: an Actions workflow cannot be executed locally,
# but this can — scripts/ci/check-ai-review.test.sh runs it red (mixed
# diff, no section; rounds: 1) and green (compliant body; docs-only diff).
set -euo pipefail

files=()
while IFS= read -r line; do
  [ -n "$line" ] && files+=("$line")
done

if [ "${#files[@]}" -eq 0 ]; then
  echo "No changed files — nothing to gate."
  exit 0
fi

docs_only=true
for f in "${files[@]}"; do
  case "$f" in
    docs/*) ;;
    *.md)   ;;
    *) docs_only=false; break ;;
  esac
done

if [ "$docs_only" = true ]; then
  echo "Docs-only PR (every changed file is *.md or under docs/) — exempt from the AI-review gate."
  exit 0
fi

body="${PR_BODY-}"

ok=true
printf '%s' "$body" | grep -Eiq '^[[:space:]]*##[[:space:]]*AI review' || ok=false
printf '%s' "$body" | grep -Eiq 'rounds:[[:space:]]*2([^0-9]|$)'       || ok=false
printf '%s' "$body" | grep -Eiq 'verdict'                              || ok=false

if [ "$ok" = true ]; then
  echo "AI-review section found (rounds: 2 + verdict recorded)."
  exit 0
fi

cat >&2 <<'EOF'
FAIL: this PR touches non-docs paths, so its body must record the
different-model review (Claude-built -> Codex reviews; Codex-built ->
Claude reviews). Exactly two rounds: round 1 finds, fix the actionables,
round 2 verifies the fixes, then STOP.

Add a section like this to the PR body:

  ## AI review — rounds: 2, engine: codex, verdict: pass

Docs-only PRs (every changed file *.md or under docs/) are exempt.
Ruling: management-craft docs/2B-PROJECTS/wiki-reliability/v1/RESEARCH.md
§ 9.2 (written rule: ~/.claude/CLAUDE.md § "Different-model review gate").
EOF
exit 1
