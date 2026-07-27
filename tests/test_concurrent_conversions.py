"""Tests for the concurrent-conversion registry.

One BookConvert checkout is shared by several agent sessions. The realistic
collision is one workspace running a two-hour OCR of a scanned book while
another converts a few papers for an unrelated project — both should proceed,
neither should be surprised.

Surprise is the cost being paid. A concurrent run halves each side's CPU and
doubles resident memory; on 2026-07-27 that turned an unexplained slowdown
into an hour of process archaeology before anyone noticed two markers were
running. The registry answers "is anything else running, and for how long?"
at the moment it matters, and never blocks.
"""
import json
import os
import time

import convert


def use_temp_registry(tmp_path, monkeypatch):
    reg = tmp_path / ".active-conversions.json"
    monkeypatch.setattr(convert, "ACTIVE_CONVERSIONS", reg)
    return reg


def test_registers_and_deregisters(tmp_path, monkeypatch):
    reg = use_temp_registry(tmp_path, monkeypatch)
    convert.register_conversion("Book.pdf", "marker", time.time())
    assert [e["book"] for e in json.loads(reg.read_text())] == ["Book.pdf"]
    convert.unregister_conversion()
    assert json.loads(reg.read_text()) == []


def test_register_returns_what_was_already_running(tmp_path, monkeypatch):
    reg = use_temp_registry(tmp_path, monkeypatch)
    reg.write_text(json.dumps([{"pid": os.getpid(), "book": "Boyatzis.pdf",
                                "method": "marker", "started": time.time()}]))
    # A different pid registering sees the existing one. The real pid is
    # captured first: a lambda calling os.getpid() would call the patched
    # version and recurse forever.
    other_pid = os.getpid() + 100000
    monkeypatch.setattr(convert.os, "getpid", lambda: other_pid)
    others = convert.register_conversion("Paper.pdf", "marker", time.time())
    assert [e["book"] for e in others] == ["Boyatzis.pdf"]


def test_dead_processes_are_pruned(tmp_path, monkeypatch):
    """A killed or crashed conversion never cleans up after itself, so stale
    entries are the normal case rather than the exception. Reporting one as
    live would misdescribe the machine."""
    reg = use_temp_registry(tmp_path, monkeypatch)
    reg.write_text(json.dumps([
        {"pid": os.getpid(), "book": "Live.pdf", "method": "marker", "started": time.time()},
        {"pid": 999999999, "book": "Dead.pdf", "method": "marker", "started": time.time()},
    ]))
    assert [e["book"] for e in convert.read_active_conversions()] == ["Live.pdf"]


def test_a_corrupt_registry_is_ignored_not_fatal(tmp_path, monkeypatch):
    """Advisory only. A malformed file must never stop a conversion."""
    reg = use_temp_registry(tmp_path, monkeypatch)
    reg.write_text("{ not json")
    assert convert.read_active_conversions() == []
    convert.register_conversion("Book.pdf", "marker", time.time())
    assert [e["book"] for e in json.loads(reg.read_text())] == ["Book.pdf"]


def test_missing_registry_is_ignored(tmp_path, monkeypatch):
    use_temp_registry(tmp_path, monkeypatch)
    assert convert.read_active_conversions() == []


def test_unwritable_registry_does_not_fail_the_conversion(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "ACTIVE_CONVERSIONS",
                        tmp_path / "nonexistent-dir" / "reg.json")
    assert convert.register_conversion("Book.pdf", "marker", time.time()) == []
    convert.unregister_conversion()          # must not raise


def test_notice_names_the_book_and_how_long_it_has_run():
    now = time.time()
    others = [{"pid": 123, "book": "The Competent Manager.pdf",
               "method": "marker", "started": now - 95 * 60}]
    msg = convert.describe_other_conversions(others, now)
    assert "The Competent Manager.pdf" in msg
    assert "1h35m" in msg                     # duration is the actionable part
    assert "8 GB" in msg                      # so is the memory consequence


def test_notice_uses_minutes_under_an_hour():
    now = time.time()
    msg = convert.describe_other_conversions(
        [{"pid": 1, "book": "Paper.pdf", "method": "marker", "started": now - 300}], now)
    assert "5m" in msg


def test_no_notice_when_nothing_else_is_running():
    assert convert.describe_other_conversions([], time.time()) is None


def test_a_malformed_timestamp_does_not_break_the_notice():
    msg = convert.describe_other_conversions(
        [{"pid": 1, "book": "X.pdf", "method": "marker", "started": "nonsense"}],
        time.time())
    assert "unknown" in msg and "X.pdf" in msg
