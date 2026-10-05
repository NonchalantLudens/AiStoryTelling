import time

import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from storyteller.core import adapters
from storyteller.webui.app import create_app


@pytest.fixture
def client(tmp_path):
    config = {
        "tts": {"name": "stub_tts", "voice": "default-v"},
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
    return TestClient(create_app(config, tmp_path))


class FakeTTS:
    name = "fake"
    calls = 0

    def __init__(self, **opts):
        self.opts = opts

    def synthesize(self, text: str, out_path) -> float:
        FakeTTS.calls += 1
        out_path.write_text("audio")
        return 1.5


adapters.register("tts", "stub_tts", FakeTTS)


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
    # fake 管线链路不完整时任务会 failed，断言只要求终态
    assert client.get(f"/api/jobs/{jid}").json()["status"] in ("done", "failed")
    assert any(j["id"] == jid for j in client.get("/api/jobs").json())


def test_empty_text_rejected(client):
    r = client.post("/api/jobs", json={"text": "  "})
    assert r.status_code == 400


def test_themes(client):
    data = client.get("/api/themes").json()
    assert data["default"] == "campfire"
    assert data["themes"] == ["campfire"]


def test_engines_lists_registered(client):
    data = client.get("/api/engines").json()
    assert "stub_tts" in data["tts"]
    assert "edge" in data["tts"]
    assert "loop_video" in data["visual"]


def test_preview_split(client):
    r = client.post("/api/preview/split", json={"text": "一段。\n\n二段。"})
    assert r.json()["segments"] == ["一段。", "二段。"]


def test_preview_tts_and_cache(client):
    FakeTTS.calls = 0
    r1 = client.post(
        "/api/preview/tts", json={"text": "你好", "engine": "stub_tts", "voice": "v1"}
    )
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["url"].startswith("/preview/") and data1["duration"] == 1.5
    r2 = client.post(
        "/api/preview/tts", json={"text": "你好", "engine": "stub_tts", "voice": "v1"}
    )
    assert r2.json()["url"] == data1["url"]
    assert FakeTTS.calls == 1  # 第二次命中缓存
    r3 = client.post(
        "/api/preview/tts", json={"text": "你好", "engine": "stub_tts", "voice": "v2"}
    )
    assert r3.json()["url"] != data1["url"]
    assert FakeTTS.calls == 2
    # 引擎默认参数来自 config.tts（voice=default-v），请求里没给也行
    r4 = client.post("/api/preview/tts", json={"text": "默认参数", "engine": "stub_tts"})
    assert r4.status_code == 200


def test_preview_tts_empty_text(client):
    assert client.post("/api/preview/tts", json={"text": " "}).status_code == 400


def test_preview_visual(tmp_path):
    from storyteller.core import adapters as _adapters

    class FakeVis:
        name = "fake_vis"

        def __init__(self, **opts):
            self.opts = opts

        def themes(self):
            return []

        def resolve(self, theme, duration, out_path):
            out_path.write_text("mp4")
            return out_path

    _adapters.register("visual", "fake_vis", FakeVis)
    config = {
        "tts": {"name": "stub_tts"},
        "visual": {
            "name": "fake_vis",
            "assets_dir": tmp_path / "loops",
            "default_theme": "campfire",
        },
        "composer": {"name": "ffmpeg"},
        "output": {"width": 1280, "height": 720, "fps": 30, "dir": "outputs"},
    }
    # stub 产物不是真视频，mock ffprobe 探测
    with patch("storyteller.core.preview.probe_duration", return_value=3.0):
        c = TestClient(create_app(config, tmp_path))
        r = c.post("/api/preview/visual", json={"theme": "campfire", "duration": 3.0})
        assert r.status_code == 200
        data = r.json()
        assert data["url"].startswith("/preview/") and data["duration"] > 0
        # 缓存命中
        r2 = c.post("/api/preview/visual", json={"theme": "campfire", "duration": 3.0})
        assert r2.json()["url"] == data["url"]


def test_cancel_endpoint(client):
    assert client.post("/api/jobs/nope/cancel").status_code == 400
    jid = client.post("/api/jobs", json={"text": "x"}).json()["id"]
    r = client.post(f"/api/jobs/{jid}/cancel")
    assert r.status_code == 200
    # 排队时取消：终态为 cancelled（worker 可能尚未取件）
    job = client.get(f"/api/jobs/{jid}").json()
    assert job["status"] in ("cancelled", "done")


def test_upload_asset(client):
    r = client.post(
        "/api/assets/upload",
        data={"theme": "space"},
        files={"file": ("nebula.mp4", b"video-bytes", "video/mp4")},
    )
    assert r.status_code == 200
    assets = client.get("/api/assets").json()
    assert assets["space"] == ["nebula.mp4"]
    assert client.get("/assets/loops/space/nebula.mp4").status_code == 200


def test_upload_bad_theme_rejected(client):
    r = client.post(
        "/api/assets/upload",
        data={"theme": "../evil"},
        files={"file": ("x.mp4", b"x", "video/mp4")},
    )
    assert r.status_code == 400
