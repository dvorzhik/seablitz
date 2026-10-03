"""Тесты бота: разбор кода комнаты и построение ссылки на Mini App."""
from __future__ import annotations

from bot.main import extract_code, start_caption, webapp_url


def test_extract_code_with_prefix():
    assert extract_code("blitz-ABCD") == "ABCD"
    assert extract_code("blitz ab12") == "AB12"
    assert extract_code("blitz:xy9z") == "XY9Z"
    assert extract_code("Blitz-Q7W2") == "Q7W2"


def test_extract_code_bare():
    assert extract_code("q7w2") == "Q7W2"
    assert extract_code("  AB12  ") == "AB12"


def test_extract_code_none():
    assert extract_code("blitz") is None
    assert extract_code("") is None
    assert extract_code("hello world") is None


def test_webapp_url_has_startapp():
    url = webapp_url("ABCD")
    assert url.startswith("https://t.me/")
    assert "startapp=ABCD" in url


def test_webapp_url_without_param():
    url = webapp_url()
    assert url.startswith("https://t.me/")
    assert "startapp" not in url


def test_start_caption_mentions_brand_and_username():
    caption = start_caption()
    assert "SeaBlitz" in caption
    assert "Играть" in caption
    # username всегда присутствует (с фолбэком на seablitz_bot).
    assert "@" in caption
