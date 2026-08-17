"""marker 2.0 is a correctness floor, and the docs that get someone there must agree.

marker 1.10.2 hallucinates on blank pages: with nothing to transcribe it emits a repeating
n-gram to a token cap, ~2,046 characters of prose-shaped text that was never in the book.
So the pin is not a preference, and it is not enough on its own — 2.x also needs a
`llama-server` binary that pip cannot install, and it fails at the END of a long
conversion without it.

Per the enforced-invariant rule: when a requirement becomes enforced, every documented
path that produces it changes in the same commit. These tests are that rule made
mechanical, so the pin and the install docs cannot drift apart silently.

See 8-DECISIONS/2026-08-17-marker-2-adoption.md.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQS = (ROOT / "requirements-marker.txt").read_text()


def test_marker_is_pinned_to_2_or_newer():
    m = re.search(r"^marker-pdf\s*(.*)$", REQS, re.M)
    assert m, "requirements-marker.txt no longer pins marker-pdf at all"
    spec = m.group(1).strip()
    assert spec, (
        "marker-pdf is unpinned. An unpinned install silently accepts 1.x, which writes "
        "text that was never in the book."
    )
    floor = re.match(r">=\s*(\d+)", spec)
    assert floor and int(floor.group(1)) >= 2, f"marker-pdf floor is {spec!r}, must be >=2.0.0"


def test_the_system_dependency_is_documented_where_someone_installing_will_see_it():
    """A pin that produces an unexplained crash is a trap, not a fix. The llama.cpp
    requirement has to appear in the file the installer reads AND in the README block
    that tells them what to run."""
    assert "llama.cpp" in REQS, "requirements-marker.txt does not mention llama.cpp"
    readme = (ROOT / "README.md").read_text()
    assert "brew install llama.cpp" in readme, "README does not give the install command"
    assert "llama-server" in readme, "README does not name the error the operator will see"


def test_the_reason_for_the_floor_is_recorded_not_just_the_floor():
    """A bare version pin invites someone to relax it. The requirements file has to say
    what breaks, so the next person reads a reason rather than a number."""
    assert re.search(r"hallucinat|never in the book", REQS, re.I), (
        "requirements-marker.txt pins a floor without saying why 1.x is unsafe"
    )
    assert (ROOT / "8-DECISIONS" / "2026-08-17-marker-2-adoption.md").exists()
