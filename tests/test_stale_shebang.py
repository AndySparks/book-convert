"""Tests for stale-venv-shebang detection.

Renaming the project directory leaves every venv console script pointing at an
interpreter that no longer exists. The script still exists and `shutil.which`
still finds it, so the existence check in check_dependencies() passes and the
failure only surfaces when the binary is spawned -- as a `bad interpreter`
error that never mentions the rename. These cover the detector that closes
that gap.
"""
import os
import sys

import pytest

import convert


def _script(tmp_path, name, first_line):
    p = tmp_path / name
    p.write_text(first_line + "\n# body\n")
    p.chmod(0o755)
    return p


def test_dead_absolute_interpreter_is_reported(tmp_path):
    """The real failure: shebang names an absolute path that is gone."""
    dead = "/Users/nobody/projects/BookConvert/.venv-marker/bin/python3.12"
    s = _script(tmp_path, "marker_single", f"#!{dead}")
    assert convert._stale_shebang(s) == dead


def test_live_absolute_interpreter_is_not_reported(tmp_path):
    """A shebang pointing at a real interpreter is fine."""
    s = _script(tmp_path, "marker_single", f"#!{sys.executable}")
    assert convert._stale_shebang(s) is None


def test_env_shebang_is_not_reported(tmp_path):
    """`/usr/bin/env python3` resolves against PATH at spawn time.

    There is no absolute interpreter to verify, so claiming it is stale would
    be a false positive that blocks a working conversion.
    """
    s = _script(tmp_path, "marker_single", "#!/usr/bin/env python3")
    assert convert._stale_shebang(s) is None


def test_relative_interpreter_is_not_reported(tmp_path):
    """Only absolute paths are checkable; anything else is left alone."""
    s = _script(tmp_path, "marker_single", "#!python3")
    assert convert._stale_shebang(s) is None


def test_non_shebang_file_is_not_reported(tmp_path):
    """A binary or a plain file must not be diagnosed as a broken script."""
    s = _script(tmp_path, "marker_single", "not a shebang at all")
    assert convert._stale_shebang(s) is None


def test_missing_file_is_not_reported(tmp_path):
    """Unreadable path returns None rather than raising.

    This is a diagnostic run inside a dependency check; it must never be the
    reason a conversion refuses to start.
    """
    assert convert._stale_shebang(tmp_path / "does-not-exist") is None


def test_empty_file_is_not_reported(tmp_path):
    s = tmp_path / "marker_single"
    s.write_text("")
    assert convert._stale_shebang(s) is None


def test_shebang_with_arguments_uses_the_interpreter(tmp_path):
    """`#!/path/to/python -u` -- the interpreter is the first token."""
    dead = "/gone/bin/python3.12"
    s = _script(tmp_path, "marker_single", f"#!{dead} -u")
    assert convert._stale_shebang(s) == dead


def test_check_dependencies_raises_on_stale_marker(tmp_path, monkeypatch):
    """End to end: a stale marker_single beside sys.executable is caught.

    Without this, check_dependencies() passes and the conversion dies minutes
    later with an error that does not name the cause.
    """
    if sys.version_info < (3, 10):
        pytest.skip("marker path requires Python 3.10+")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "python").write_text("#!/bin/sh\n")
    dead = "/Users/nobody/projects/BookConvert/.venv-marker/bin/python3.12"
    _script(fake_bin, "marker_single", f"#!{dead}")

    monkeypatch.setattr(sys, "executable", str(fake_bin / "python"))
    # Keep the PATH lookup from finding a healthy marker_single elsewhere.
    monkeypatch.setenv("PATH", str(fake_bin))

    with pytest.raises(convert.DependencyError) as exc:
        convert.check_dependencies("marker")

    msg = str(exc.value)
    assert "bad interpreter" in msg
    assert dead in msg


# --- the guard must cover the path people actually take --------------------

def test_marker_spawn_rejects_a_dead_interpreter_even_with_skip_check(tmp_path, monkeypatch):
    """`--skip-check` skips check_dependencies, so the spawn must check too.

    Every documented invocation passes --skip-check: mc-wiki's
    ingest-batch.sh and four places in source-ingestion.md. When sourceconvert
    moved to ~/conductor/repos on 2026-07-29, all 125 venv scripts kept
    pointing at the old location and the check added that same morning could
    not fire, because it lived behind the flag everyone sets.
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    dead = "/Users/nobody/Documents/Claude/projects/sourceconvert/.venv-marker/bin/python3.12"
    s = fake_bin / "marker_single"
    s.write_text(f"#!{dead}\n")
    s.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(convert.ConversionError) as exc:
        convert.convert_with_marker(pdf, tmp_path / "out")

    msg = str(exc.value)
    assert dead in msg
    # The repair hint must name the old root so the sed is copy-pasteable.
    assert "/Users/nobody/Documents/Claude/projects/sourceconvert" in msg


def test_marker_spawn_allows_a_healthy_interpreter(tmp_path, monkeypatch):
    """The guard must not block a working marker: no raise before spawn."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    s = fake_bin / "marker_single"
    s.write_text(f"#!{sys.executable}\n")
    s.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))
    assert convert._stale_shebang(s) is None
