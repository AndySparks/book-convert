"""Tests for check_dependencies gating."""
import sys

import pytest

import convert


def test_check_dependencies_pymupdf4llm_on_old_python():
    """On Python 3.9, check_dependencies should raise with a helpful message."""
    if sys.version_info >= (3, 10):
        pytest.skip("Test only meaningful on Python 3.9")
    with pytest.raises(convert.DependencyError, match=r"pymupdf4llm"):
        convert.check_dependencies("pymupdf4llm")


def test_check_dependencies_pymupdf4llm_on_new_python():
    """On Python 3.10+, check_dependencies should succeed if pymupdf4llm is installed."""
    if sys.version_info < (3, 10):
        pytest.skip("Test only meaningful on Python 3.10+")
    try:
        import pymupdf4llm  # noqa: F401
    except ImportError:
        pytest.skip("pymupdf4llm not installed in this interpreter")
    convert.check_dependencies("pymupdf4llm")


def test_check_dependencies_docling_on_old_python():
    if sys.version_info >= (3, 10):
        pytest.skip("Test only meaningful on Python 3.9")
    with pytest.raises(convert.DependencyError, match=r"docling"):
        convert.check_dependencies("docling")


def test_cli_accepts_pymupdf4llm_method():
    """main() should accept --method pymupdf4llm without argparse error."""
    import sys as _sys

    old_argv = _sys.argv
    try:
        _sys.argv = ["convert.py", "nonexistent.pdf", "--method", "pymupdf4llm", "--skip-check"]
        with pytest.raises(SystemExit):
            convert.main()
    finally:
        _sys.argv = old_argv


def test_cli_accepts_docling_method():
    import sys as _sys

    old_argv = _sys.argv
    try:
        _sys.argv = ["convert.py", "nonexistent.pdf", "--method", "docling", "--skip-check"]
        with pytest.raises(SystemExit):
            convert.main()
    finally:
        _sys.argv = old_argv
