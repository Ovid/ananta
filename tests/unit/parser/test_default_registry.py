"""Tests for default parser registry."""

from pathlib import Path

from ananta.parser import create_default_registry


def test_default_registry_has_text_parser():
    """Default registry can parse text files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.txt")) is not None


def test_default_registry_has_code_parser():
    """Default registry can parse code files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.py")) is not None


def test_default_registry_has_pdf_parser():
    """Default registry can parse PDF files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.pdf")) is not None


def test_default_registry_has_html_parser():
    """Default registry can parse HTML files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.html")) is not None


def test_default_registry_has_docx_parser():
    """Default registry can parse docx files."""
    registry = create_default_registry()
    assert registry.find_parser(Path("test.docx")) is not None


def test_default_registry_has_fallback_parser(tmp_path: Path):
    """Default registry can parse unknown text files via fallback."""
    registry = create_default_registry()
    # Create a file with unknown extension that contains text
    unknown_file = tmp_path / "config.xyz"
    unknown_file.write_text("some=config\nkey=value")
    # Fallback parser should catch it
    assert registry.find_parser(unknown_file) is not None
