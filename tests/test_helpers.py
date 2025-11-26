# tests/test_helpers.py
import main


def test_humanbytes_small():
    assert main.humanbytes(512) == "512  B"


def test_humanbytes_kib():
    text = main.humanbytes(2048)
    assert text.startswith("2.0")
    assert "KiB" in text


def test_humanbytes_zero():
    assert main.humanbytes(0) == ""
