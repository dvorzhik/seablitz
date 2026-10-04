"""Тесты шаринга картинки результата (OG-превью для Telegram)."""
from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 1x1 PNG
PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_share_roundtrip():
    resp = client.post(
        "/api/share",
        json={"image": PNG, "title": "@a победил @b", "text": "Сыграй в SeaBlitz"},
    )
    assert resp.status_code == 200
    url = resp.json()["url"]
    assert "/s/" in url
    token = url.rsplit("/s/", 1)[1]

    page = client.get(f"/s/{token}")
    assert page.status_code == 200
    assert "og:image" in page.text
    assert f"/s/{token}/card.png" in page.text

    img = client.get(f"/s/{token}/card.png")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content == base64.b64decode(PNG.split(",", 1)[1])


def test_share_requires_image():
    assert client.post("/api/share", json={"title": "x"}).status_code == 400
    assert client.post("/api/share", json={"image": "nope"}).status_code == 400


def test_share_not_found():
    assert client.get("/s/nope").status_code == 404
    assert client.get("/s/nope/card.png").status_code == 404
