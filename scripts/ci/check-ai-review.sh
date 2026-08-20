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
#         in $PR_BODY. Optionally $PR_CHANGED_FILES (the PR API's
#         changed_files count) and $PR_LISTED_FILES (how many entries the
#         file listing actually returned): the pulls/files endpoint caps
#         at 3,000 entries, so listed < changed means the listing is
#         truncated and the diff CANNOT be classified — fail closed by
#         treating the PR as mandatory-review.
# Exempt (sourceconvert: everything in this repo IS conversion code, so
#         the exemption is narrow): *.md under docs/, and root-level *.md
#         EXCEPT CLAUDE.md (an agent contract over conversion behavior,
#         not prose). Everything else — convert.py, scripts/, tests/,
#         .github/, output/, requirements — is mandatory-review.
# Pass:   otherwise, when the body carries ONE `## AI review` section
#         (heading to the next `## ` or EOF) and INSIDE that slice:
#         "rounds: 2" (exactly 2 — 1, 12, 2+, 2.5 fail; sentence-final
#         "2." passes), an engine with a real value, and a verdict with a
#         real value (a bare "engine: ," or "verdict:" fails; template
#         text elsewhere in the body supplies nothing). Lenient on
#         formatting, strict on those facts.
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

# Fail closed on a truncated file listing (pulls/files caps at 3,000).
truncated=false
if [ -n "${PR_CHANGED_FILES-}" ] && [ -n "${PR_LISTED_FILES-}" ] \
   && [ "${PR_LISTED_FILES}" -lt "${PR_CHANGED_FILES}" ]; then
  truncated=true
  echo "File listing truncated (${PR_LISTED_FILES} of ${PR_CHANGED_FILES} entries) — PR too large to classify; treating as mandatory-review."
fi

docs_only=true
if [ "$truncated" = true ]; then
  docs_only=false
else
  for f in "${files[@]}"; do
    if ! exempt "$f"; then
      docs_only=false
      break
    fi
  done
fi

if [ "$docs_only" = true ]; then
  echo "Docs-only PR (every changed file *.md under docs/ or at the root, none an agent contract) — exempt from the AI-review gate."
  exit 0
fi

body="${PR_BODY-}"

# Extract ONE section: the first `## AI review` heading through the line
# before the next `## ` heading (or EOF). All field checks run inside this
# slice, so stale template text elsewhere in the body supplies nothing —
# and <!-- --> comment content (same-line spans AND multi-line blocks) is
# stripped first, so a commented-out template supplies nothing either.
section=$(printf '%s\n' "$body" | awk '
  {
    # Close a comment block opened on an earlier line.
    if (incomment) {
      e = index($0, "-->")
      if (e == 0) next
      $0 = substr($0, e + 3)
      incomment = 0
    }
    # Strip complete same-line <!-- ... --> spans; an unclosed opener
    # drops the rest of the line and opens a block.
    while ((s = index($0, "<!--")) > 0) {
      rest = substr($0, s + 4)
      e = index(rest, "-->")
      if (e == 0) { $0 = substr($0, 1, s - 1); incomment = 1; break }
      $0 = substr($0, 1, s - 1) substr(rest, e + 3)
    }
    if (insec && $0 ~ /^[[:space:]]*## /) exit
    if (insec) { print; next }
    if (tolower($0) ~ /^[[:space:]]*##[[:space:]]*ai review/) { insec = 1; print }
  }
')

# Field values are bounded at commas/semicolons/whitespace BEFORE requiring
# an alphanumeric, so an empty field cannot consume the next label
# ("engine:,verdict:pass" is an empty engine, not engine=",verdict:pass").
# rounds accepts a sentence-final "2." only at a real token boundary
# (whitespace or end of line) — "2.5" and "2.foo" both fail.
ok=true
[ -n "$section" ] || ok=false
printf '%s' "$section" | grep -Eiq 'rounds:[[:space:]]*2([[:space:],;)]|\.([[:space:]]|$)|$)'   || ok=false
printf '%s' "$section" | grep -Eiq 'engine[:[:space:]][[:space:]]*[^,;[:space:]]*[[:alnum:]]'  || ok=false
printf '%s' "$section" | grep -Eiq 'verdict[:[:space:]][[:space:]]*[^,;[:space:]]*[[:alnum:]]' || ok=false

if [ "$ok" = true ]; then
  echo "AI-review section found (rounds: 2 + engine + verdict recorded)."
  exit 0
fi

cat >&2 <<'EOF'
FAIL: this PR touches conversion code or other non-docs paths, so its
body must record the different-model review (Claude-built -> Codex
reviews; Codex-built -> Claude reviews). Exactly two rounds: round 1
finds, fix the actionables, round 2 verifies the fixes, then STOP.

Add ONE section like this to the PR body — all three fields, with real
values, inside the section itself:

  ## AI review — rounds: 2, engine: codex, verdict: pass

Docs-only PRs (every changed file *.md under docs/ or at the repo root,
CLAUDE.md excluded) are exempt.
Ruling: management-craft docs/2B-PROJECTS/wiki-reliability/v1/RESEARCH.md
§ 9.2 (written rule: ~/.claude/CLAUDE.md § "Different-model review gate").
EOF
exit 1
