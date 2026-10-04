import time

import pytest
from fastapi.testclient import TestClient

from storyteller.webui.app import create_app


@pytest.fixture
def client(tmp_path):
    config = {
        "tts": {"name": "edge"},
        "visual": {
            "name": "loop_video",
            "assets_dir": tmp_path / "loops",
            "default_theme": "campfire",
        },
        "composer": {"name": "ffmpeg"},
        "output": {"width": 1280, "height": 720, "fps": 30, "dir": "outputs"},
    }
    (tmp_path / "loops" / "campfire").mkdir(parents=True)
    (tmp_path / "loops" / "campfire" / "a.mp4").write_bytes(b"stub")
    app = create_app(config, tmp_path)
    return TestClient(app)


def test_submit_and_poll(client):
    r = client.post(
        "/api/jobs",
        json={"text": "第一段。\n\n第二段。", "overrides": {"theme": "campfire"}},
    )
    assert r.status_code == 200
    jid = r.json()["id"]
    for _ in range(200):
        job = client.get(f"/api/jobs/{jid}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    # edge 真跑，可能因网络环境失败，断言只要求终态
    assert client.get(f"/api/jobs/{jid}").json()["status"] in ("done", "failed")
    assert any(j["id"] == jid for j in client.get("/api/jobs").json())


def test_empty_text_rejected(client):
    r = client.post("/api/jobs", json={"text": "  "})
    assert r.status_code == 400


def test_themes(client):
    data = client.get("/api/themes").json()
    assert data["default"] == "campfire"
    assert data["themes"] == ["campfire"]
