#!/usr/bin/env bash
# check-ai-review.sh — the different-model review-gate predicate
# (wiki-reliability Phase 4.2, ruling § 9.2: management-craft
# docs/2B-PROJECTS/wiki-reliability/v1/RESEARCH.md; written rule at
# ~/.claude/CLAUDE.md § "Different-model review gate").
#
# PRs that touch anything beyond documentation get a different-model
# review — exactly two rounds — recorded in the PR body as an
# `## AI review` section. This script is the whole predicate; the workflow
# (.github/workflows/ai-review-gate.yml) only feeds it.
#
# Input:  changed file paths on stdin, one per line — for renames the
#         workflow feeds BOTH sides (filename + previous_filename), so a
#         code file renamed into docs/ still reads as code; the PR body
#         in $PR_BODY.
# Exempt (sourceconvert: everything in this repo IS conversion code, so
#         the exemption is narrow): *.md under docs/, and root-level *.md
#         EXCEPT CLAUDE.md (an agent contract over conversion behavior,
#         not prose). Everything else — convert.py, scripts/, tests/,
#         .github/, output/, requirements — is mandatory-review.
# Pass:   otherwise, when the body contains an `## AI review` heading,
#         "rounds: 2" (exactly 2 — 1, 12, 2+, 2.5 all fail), a named
#         engine, and a verdict. Lenient on formatting, strict on those
#         four facts.
# Exit 0 pass / 1 fail.
#
# Standalone on purpose: an Actions workflow cannot be executed locally,
# but this can — scripts/ci/check-ai-review.test.sh runs it red and green.
set -euo pipefail

exempt() {  # $1 = path; docs-shaped?
  case "$1" in
    CLAUDE.md) return 1 ;;  # agent contract, never exempt
    docs/*.md) return 0 ;;  # markdown under docs/ (any depth)
    */*)       return 1 ;;  # every other nested path is code/corpus
    *.md)      return 0 ;;  # root-level markdown (README, ROADMAP, ...)
  esac
  return 1
}

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
  if ! exempt "$f"; then
    docs_only=false
    break
  fi
done

if [ "$docs_only" = true ]; then
  echo "Docs-only PR (every changed file *.md under docs/ or at the root, none an agent contract) — exempt from the AI-review gate."
  exit 0
fi

body="${PR_BODY-}"

ok=true
printf '%s' "$body" | grep -Eiq '^[[:space:]]*##[[:space:]]*AI review'        || ok=false
printf '%s' "$body" | grep -Eiq 'rounds:[[:space:]]*2([[:space:],;)]|$)'      || ok=false
printf '%s' "$body" | grep -Eiq 'engine[:[:space:]][[:space:]]*[^[:space:]]+' || ok=false
printf '%s' "$body" | grep -Eiq 'verdict'                                     || ok=false

if [ "$ok" = true ]; then
  echo "AI-review section found (rounds: 2 + engine + verdict recorded)."
  exit 0
fi

cat >&2 <<'EOF'
FAIL: this PR touches conversion code or other non-docs paths, so its
body must record the different-model review (Claude-built -> Codex
reviews; Codex-built -> Claude reviews). Exactly two rounds: round 1
finds, fix the actionables, round 2 verifies the fixes, then STOP.

Add a section like this to the PR body:

  ## AI review — rounds: 2, engine: codex, verdict: pass

Docs-only PRs (every changed file *.md under docs/ or at the repo root,
CLAUDE.md excluded) are exempt.
Ruling: management-craft docs/2B-PROJECTS/wiki-reliability/v1/RESEARCH.md
§ 9.2 (written rule: ~/.claude/CLAUDE.md § "Different-model review gate").
EOF
exit 1
