---
type: decision
date: 2026-07-28
status: accepted
tags: [naming, vocabulary, scope]
---

# BookConvert becomes sourceconvert

## Decision

Rename the project — GitHub repo, local directory, and every load-bearing prose
and code reference — from **BookConvert** to **sourceconvert**.

## Why

The name was scoping behaviour, not just describing it.

Andy: *"BookConvert is a bit misnamed … since it is also used for papers. And
that's part of the folder problem. I only think to use it for books, so when we
do papers they go in other places."*

That is the whole argument. The tool has always converted PDFs and EPUBs of any
kind — books, papers, reports, articles. But the name says *books*, so papers
routed around it and landed in ad-hoc folders. **The routing-around was the
folder sprawl.** Three separate inboxes existed (`input/`, `~/Documents/Book
Scans/`, and chat attachments) partly because the tool's name made only one of
them feel like the right door.

The consuming vault already had the right word. Its notes are **sources**, with
`type: book | paper | article | report | talk`, a `source_class` field, and a
runbook called `source-ingestion.md`. The tooling was the last layer still
saying "book."

## Scope, and what was deliberately not swept

Swept: GitHub repo name, the local directory path, and prose plus code across
sourceconvert, mc-wiki, Management Craft docs, and `~/.claude` runbooks and
rules. 35 files, 162 replacements.

**Not swept — frozen history**, per `retired-vocabulary.md`'s rule that history
is preserved as authored:

- `raw/*.md` bodies and provenance (28 files). These record what was true when
  written; a naive `grep -rl … | xargs sed` would have rewritten the corpus's
  own account of itself.
- `8-DECISIONS/` in both repos, and `log.md` (42 mentions). Decision docs and
  chronological records are immutable.
- Completed bet records, dictations, retros and PROGRESS files in MC.

The distinction applied throughout: sweep artifacts that *instruct future
behaviour*, leave artifacts that *record what happened*.

## The gate

Not "no matches for the old name." Every documented command was executed:
sourceconvert's suite (310 passed, 8 skipped), every gate in `mc-wiki/tools/`,
and `npm run validate` in Management Craft. A passing grep with a broken command
is exactly the half-retirement the vocabulary rule exists to prevent.

`scripts/extract_hbr.sh` hardcoded the old absolute path and was genuinely
broken by the directory rename — found and fixed by this gate rather than by a
grep.

## Notes

- GitHub redirects the old URL, so existing clones keep working. Remotes were
  updated anyway, on both machines.
- Not published to PyPI, so no registry breakage. 4 stars, 0 forks — negligible
  external footprint.
- `STRIPPED_REF_COMMENT`, a wire-format string written into converted markdown,
  was changed as part of this. Safe only because it had not yet been emitted
  into any filed source (verified: 0 files). After Phase 6 it would have been
  costly.
- Timing: the pipeline (source-pipeline Phase 5) does not exist yet, so nothing
  built on the old name needed re-sweeping. The project PLAN said rename last;
  that reasoning assumed the pipeline existed, and doing it now means everything
  built afterward uses the right name from the start.

## See also

- `~/conductor/workspaces/management-craft/montpelier/docs/2B-PROJECTS/source-pipeline/`
  — the bet this rename belongs to.
- `.claude/rules/retired-vocabulary.md` — the row recording the retirement.
