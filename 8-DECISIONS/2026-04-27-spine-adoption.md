---
type: decision
date: 2026-04-27
last_updated: 2026-04-27
slug: spine-adoption
status: accepted
scope: bookconvert
tags: [spine, spine-adoption, methodology]
supersedes: []
invalidates: []
ceremony: y-statement
---

# BookConvert adopts spine (partial — vocabulary + decision pattern + roadmap rename)

In the context of the 2026-04-27 cross-project spine-portability decision (`~/operating-system/8-DECISIONS/2026-04-27-spine-portability.md`) framing spine as a portable methodology, with OS as canonical reference and per-repo adoption gated on each repo's own work warranting migration, and BookConvert being a small tooling repo (PDF/EPUB → Markdown converter, ~10 source files, thin docs surface) explicitly without its own STRATEGY (per the existing CLAUDE.md, strategic context lives upstream in MC), facing the choice between (a) deferring spine adoption since BookConvert's footprint is small and stable, (b) adopting full spine ceremony with `2-PROJECTS/`, B+C-lite validator + pre-commit, and the rest, or (c) **adopting partial spine — vocabulary lock, decision-file pattern, and roadmap rename — without ceremony that doesn't fit a tooling repo's shape** — we chose (c), to gain the rules-collapse value (one cross-repo navigation pattern; future decisions land in a spine-aligned location instead of accumulating as `docs/<topic>-decision.md` files) — over (a) which would let BookConvert remain off-spine while teaching, MC's wiki-engine, and OS converge on a shared convention, and (b) which would force project ceremony that the repo's tooling shape doesn't earn.

## What changed

1. **`docs/TASKS.md` renamed to `1-ROADMAP.md`.** Frontmatter added (`type: roadmap`, `scope: bookconvert`, `status: active`, `last_updated: 2026-04-27`). Same role — Now / Next / Blocked / Someday punch list loaded at session start. Aligns the load-bearing nav file with spine's canonical name and lifts it to the repo root (matches OS + teaching pattern).
2. **`8-DECISIONS/` directory created.** This decision file is its first inhabitant. Future decisions live here following spine convention (`YYYY-MM-DD-slug.md` + Y-statement / directive / full ceremony).
3. **`CLAUDE.md` updated.** Notes that the repo is partially spined; points at the spine portability decision for vocabulary; replaces the old `@docs/TASKS.md` session-start pointer with `@1-ROADMAP.md`.

## Explicit divergences from OS reference

These are intentional, not drift:

- **No `0-STRATEGY.md`.** Strategic context lives upstream in MC's `docs/0-STRATEGY.md` under the MC Research Loop Acquire step. Pre-existing CLAUDE.md framing; preserved.
- **No `2-PROJECTS/`.** BookConvert's project shape is the converter itself, not multi-version sub-projects. The existing `docs/` folder carries decision-shaped artifacts (`paper-extraction-decision.md`, `paper-extraction-research.md`, `paper-extraction-results.md`, `quality-fallback-design.md`, `quality-fallback-plan.md`, `bookconvert-improvements-plan-2026-04-15.md`) — these are candidates for future migration to `8-DECISIONS/` or a `2-PROJECTS/<name>/` layout, but moving them in this PR would conflate adoption with reorganization. Defer.
- **No `3-RULES/`.** Tooling repo; no separate rules surface needed beyond CLAUDE.md.
- **No `7-RUNBOOKS/`.** Workflow lives in CLAUDE.md and the `convert.py` CLI. If a multi-step operational workflow surfaces (e.g., a recurring BookConvert-on-fleet-of-PDFs pipeline), file then.
- **No B+C-lite validator + pre-commit hook.** Repo is too small for the scaffolding to earn its keep. Revisit if decision/runbook count grows past ~5 each.
- **No `_archive/` convention yet.** Establish when the first artifact actually warrants archive.

## What's NOT changing

- Source code (`convert.py`, `assets.py`, `report.py`, `scripts/`, `tests/`) untouched.
- `docs/` retains its existing five decision-research-design-plan markdowns. They're loose-shaped relative to spine but load-bearing for current work; reorganizing them is a separate decision.
- `README.md`, `LICENSE`, `requirements*.txt`, language-runtime layouts (`.venv*`) all unchanged.
- `input/`, `output/`, `archive/`, `assets/` workflow directories unchanged.

## Future spine-adoption follow-ups (not committed to today)

- **Migrate `docs/paper-extraction-decision.md`** into `8-DECISIONS/` with proper Y-statement frontmatter. The file is decision-shaped; current location is a legacy convention.
- **Reorganize `docs/quality-fallback-design.md` + `quality-fallback-plan.md`** as a sub-bet under `2-PROJECTS/quality-fallback/` if that work resumes.
- **Consider promoting `docs/bookconvert-improvements-plan-2026-04-15.md`** to `_archive/` since it's dated and presumably reflects shipped or stale work.

These are explicitly NOT in scope for this PR. File when the next BookConvert work warrants touching the surface.

## Re-eval triggers

- BookConvert work resumes at >1 session/week → revisit the divergences as the surface grows.
- Decision count in `8-DECISIONS/` reaches ~5 → consider B+C-lite enforcement.
- Strategic divergence from MC emerges (BookConvert sprouts independent direction) → file `0-STRATEGY.md`.

## Related

- `~/operating-system/8-DECISIONS/2026-04-27-spine-portability.md` — cross-project spine portability decision. This is the third instance (after MC's wiki-engine and teaching's full-repo adoption).
- `~/conductor/repos/management-craft/docs/8-DECISIONS/2026-04-27-wiki-engine-spine-adoption.md` — first per-surface adoption (sibling instance).
- `~/teaching/8-DECISIONS/2026-04-27-spine-adoption.md` — second adoption (sibling instance).
- `~/operating-system/2-PROJECTS/spine/v1/SPEC.md` — authoritative spine specification.
