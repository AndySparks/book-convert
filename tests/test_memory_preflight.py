"""Tests for the pre-conversion memory warning.

marker holds ~8.6 GB of model weights resident. On a machine with no free RAM
the run does not fail, it crawls: Ross & Nisbett ran ~50x slower per text unit
than Boyatzis on the same laptop (0.14 vs 7 units/sec) purely because free
memory had fallen to ~94 MB. A one-hour conversion became a thirteen-hour one,
and nothing in the output said why.

The warning must never block a conversion — a wrong guess about headroom
stopping work the user asked for is worse than a slow run.
"""
import subprocess

import pytest

import convert


VM_STAT_HEALTHY = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                             1157727.
Pages active:                           2000000.
Pages inactive:                          300000.
Pages purgeable:                          42273.
Pages occupied by compressor:             10000.
"""

# The machine that prompted the fix: 0.21 GB genuinely free, 22.6 GB
# compressed, marker crawling. Note the large `Pages inactive` — counting it
# as available is what made the first version of this check report
# "18.1 GB free" and stay silent.
VM_STAT_STARVED = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               13500.
Pages active:                           2000000.
Pages inactive:                         1142478.
Pages purgeable:                          26000.
Pages occupied by compressor:           1477849.
"""


def fake_run(stdout, returncode=0):
    def _run(*_a, **_k):
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")
    return _run


def test_free_memory_counts_free_plus_purgeable(monkeypatch):
    monkeypatch.setattr(convert.subprocess, "run", fake_run(VM_STAT_HEALTHY))
    monkeypatch.setattr(convert.sys, "platform", "darwin")
    assert convert._free_memory_gb() == pytest.approx((1157727 + 42273) * 16384 / 1024**3)


def test_inactive_pages_are_not_counted_as_available(monkeypatch):
    """The bug this fix exists for. On the starved machine, free+purgeable is
    ~0.6 GB while free+inactive is ~18 GB — and the inactive-counting version
    stayed silent while marker crawled. Inactive pages on Apple Silicon are
    largely compressor-backed; reclaiming them causes the stall being
    predicted."""
    monkeypatch.setattr(convert.subprocess, "run", fake_run(VM_STAT_STARVED))
    monkeypatch.setattr(convert.sys, "platform", "darwin")
    got = convert._free_memory_gb()
    assert got == pytest.approx((13500 + 26000) * 16384 / 1024**3)
    assert got < 1.0, "inactive pages leaked back into the availability figure"


def test_compressor_occupancy_is_read(monkeypatch):
    monkeypatch.setattr(convert.subprocess, "run", fake_run(VM_STAT_STARVED))
    monkeypatch.setattr(convert.sys, "platform", "darwin")
    assert convert._compressed_gb() == pytest.approx(1477849 * 16384 / 1024**3)


def test_a_large_compressor_is_named_when_memory_is_short(monkeypatch, capsys):
    """Apple Silicon compresses before it swaps, so a machine can be badly
    oversubscribed while reporting zero swap. The compressor is the tell."""
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: 0.2)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: 0.0)
    monkeypatch.setattr(convert, "_compressed_gb", lambda: 22.6)
    convert.warn_if_memory_is_tight(304)
    err = capsys.readouterr().err
    assert "23 GB is held in the memory compressor" in err
    assert "swap is already in use" not in err       # none is, and we don't claim it


def test_small_compressor_is_not_mentioned(monkeypatch, capsys):
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: 0.2)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: 0.0)
    monkeypatch.setattr(convert, "_compressed_gb", lambda: 1.0)
    convert.warn_if_memory_is_tight(304)
    assert "compressor" not in capsys.readouterr().err


def test_no_warning_when_memory_is_ample(monkeypatch, capsys):
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: 33.5)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: 0.0)
    monkeypatch.setattr(convert, "_compressed_gb", lambda: 0.0)
    convert.warn_if_memory_is_tight(304)
    assert capsys.readouterr().err == ""


def test_residual_swap_alone_does_not_warn(monkeypatch, capsys):
    """macOS leaves pages swapped long after the pressure is gone — this
    machine showed 1.2 GB swapped with 33 GB free right after the thrashing
    run was killed. Warning on that would cry wolf on a healthy machine."""
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: 33.5)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: 1.2)
    convert.warn_if_memory_is_tight(304)
    assert capsys.readouterr().err == ""


def test_warns_when_free_memory_is_below_what_marker_needs(monkeypatch, capsys):
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: 0.1)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: 0.0)
    convert.warn_if_memory_is_tight(304)
    err = capsys.readouterr().err
    assert "0.1 GB" in err
    assert "304-page" in err
    assert "slower" in err          # the estimate is the actionable part


def test_swap_sharpens_the_diagnosis_when_memory_is_short(monkeypatch, capsys):
    """When memory IS short, active swapping is worth naming — it tells the
    operator the slowdown has already started rather than being a forecast."""
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: 0.1)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: 19.0)
    convert.warn_if_memory_is_tight(304)
    assert "19.0 GB of swap" in capsys.readouterr().err


def test_undeterminable_memory_says_nothing(monkeypatch, capsys):
    """On a platform we cannot read, stay silent rather than guess."""
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: None)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: None)
    assert convert.warn_if_memory_is_tight(304) is None
    assert capsys.readouterr().err == ""


def test_free_memory_returns_none_off_darwin(monkeypatch):
    monkeypatch.setattr(convert.sys, "platform", "linux")
    assert convert._free_memory_gb() is None
    assert convert._swap_used_gb() is None


def test_vm_stat_failure_is_not_fatal(monkeypatch):
    monkeypatch.setattr(convert.sys, "platform", "darwin")
    monkeypatch.setattr(convert.subprocess, "run", fake_run("", returncode=1))
    assert convert._free_memory_gb() is None


def test_page_count_failure_is_not_fatal(tmp_path):
    """The page count only makes the message specific; an unreadable PDF must
    not stop the conversion before it starts."""
    bad = tmp_path / "not-a.pdf"
    bad.write_bytes(b"nonsense")
    assert convert._pdf_page_count(bad) is None


def test_swap_is_not_mentioned_when_there_is_none(monkeypatch, capsys):
    """Short on memory but not swapping is a forecast, not a diagnosis.
    Claiming swap is 'already in use' when it isn't would misdescribe the
    machine and send the operator hunting for a problem they don't have."""
    monkeypatch.setattr(convert, "_free_memory_gb", lambda: 0.1)
    monkeypatch.setattr(convert, "_swap_used_gb", lambda: 0.0)
    convert.warn_if_memory_is_tight(304)
    # "swap" appears in the general explanation of WHY it will be slow; what
    # must be absent is the claim that swapping has already started.
    assert "already in use" not in capsys.readouterr().err
