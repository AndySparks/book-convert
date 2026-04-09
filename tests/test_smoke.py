"""Smoke test to verify pytest is wired up."""
import convert  # noqa: F401  — verifies conftest.py path setup


def test_smoke():
    assert 1 + 1 == 2


def test_convert_imports():
    """convert.py imports cleanly from the test environment."""
    assert hasattr(convert, "convert_pdf")
