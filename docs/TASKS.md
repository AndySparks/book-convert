# BookConvert Tasks

> Rolling punch list. Update as work moves; drop items the moment they're done.
> Loaded into Claude sessions automatically via `CLAUDE.md`.
>
> BookConvert is a small tool and does not carry a `docs/STRATEGY.md`. For strategic context on why it exists, see the Management Craft STRATEGY.md under the MC Research Loop Acquire step. Publicly trackable bugs and features live in GitHub Issues at https://github.com/AndySparks/book-convert/issues.

## Now

_none currently_

## Next

- [ ] Route scanned books through marker-pdf when available. Tracked in GitHub issue AndySparks/book-convert#18. Requires wiring `.venv-marker` (already scaffolded, Python 3.12) into `check_dependencies("marker")` and adding a scanned-book detector that prefers marker over tesseract when both are installed. Falls back to tesseract when marker is not present. Picked up when MC ingests its next pre-ebook classic and tesseract quality becomes a blocker again.

## Blocked

_none currently_

## Someday

_none currently_

---

## How to update this file

- **Add** items as work gets deferred or surfaced during a session.
- **Remove** items the moment they're done. No archive. Git log is the history.
- **Move** items between buckets as priority shifts.
- `/start` surfaces items from "Now" and "Blocked" when opening the repo.
- `/wrap` prompts to update TASKS.md at session end.

## What does NOT go here

- **Publicly trackable bugs and features**: GitHub Issues, with a link here if blocking active work in this repo.
- **MC-wide tasks that happen to touch BookConvert**: Management Craft's `docs/TASKS.md`. BookConvert is infrastructure for MC's Research Loop Acquire step; strategic questions about the corpus live upstream.
- **Cross-project personal admin**: Notion Tasks DB.
