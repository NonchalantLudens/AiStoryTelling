import json
import threading
import time

from storyteller.core.jobs import JobManager
from storyteller.core.stt_jobs import STTJobManager


def _video_pipeline(text, options, workdir, progress=None):
    out = workdir / "final.mp4"
    out.write_text("mp4:" + text[:6])
    return out


def _wait_status(m, jid, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = m.get(jid)
        if job["status"] not in ("queued", "transcribing"):
            return job
        time.sleep(0.05)
    return m.get(jid)


def _make_manager(tmp_path, transcribe_fn, video_pipeline=_video_pipeline):
    video = JobManager({}, tmp_path, pipeline_fn=video_pipeline)
    stt = STTJobManager({}, tmp_path, video, transcribe_fn=transcribe_fn)
    return video, stt


def test_transcribe_and_auto_generate(tmp_path):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"media")
    video, stt = _make_manager(tmp_path, lambda p: "这是转写文本。")
    jid = stt.submit(media, "a.mp4")
    job = _wait_status(stt, jid)
    assert job["status"] == "done"
    assert job["text"] == "这是转写文本。"
    # 生成任务已自动入队并完成
    gen = video.get(job["gen_job_id"])
    gen = _wait_status(video, job["gen_job_id"])
    assert gen["status"] == "done"


def test_multiple_files_each_gets_own_job(tmp_path):
    video, stt = _make_manager(
        tmp_path, lambda p: f"文本-{p.name}"
    )
    ids = []
    for i in range(3):
        media = tmp_path / f"f{i}.mp3"
        media.write_bytes(b"x")
        ids.append(stt.submit(media, f"f{i}.mp3"))
    for jid in ids:
        assert _wait_status(stt, jid)["status"] == "done"
    # 每个文件对应一个独立的生成任务
    gen_ids = {stt.get(j)["gen_job_id"] for j in ids}
    assert len(gen_ids) == 3


def test_failure_no_auto_generate(tmp_path):
    video, stt = _make_manager(tmp_path, lambda p: (_ for _ in ()).throw(RuntimeError("模型加载失败")))
    media = tmp_path / "a.mp4"
    media.write_bytes(b"x")
    jid = stt.submit(media, "a.mp4")
    job = _wait_status(stt, jid)
    assert job["status"] == "failed"
    assert "模型加载失败" in job["error"]
    assert job["gen_job_id"] is None


def test_empty_text_rejected_as_failure(tmp_path):
    video, stt = _make_manager(tmp_path, lambda p: "  ")
    media = tmp_path / "a.mp4"
    media.write_bytes(b"x")
    jid = stt.submit(media, "a.mp4")
    job = _wait_status(stt, jid)
    assert job["status"] == "failed"


def test_no_auto_generate_option(tmp_path):
    video, stt = _make_manager(tmp_path, lambda p: "文本")
    media = tmp_path / "a.mp4"
    media.write_bytes(b"x")
    jid = stt.submit(media, "a.mp4", auto_generate=False)
    job = _wait_status(stt, jid)
    assert job["status"] == "done" and job["gen_job_id"] is None


def test_interrupted_on_restart(tmp_path):
    store = tmp_path / "stt_jobs.json"
    store.write_text(json.dumps([
        {"id": "old", "filename": "a.mp4", "path": "/tmp/a.mp4", "status": "transcribing",
         "text": None, "gen_job_id": None, "auto_generate": True, "gen_overrides": {},
         "error": None, "created_at": "2026-01-01T00:00:00"},
    ]), encoding="utf-8")
    video, stt = _make_manager(tmp_path, lambda p: "x")
    assert stt.get("old")["status"] == "interrupted"


def test_cancel_transcribing(tmp_path):
    started = threading.Event()

    def slow_transcribe(p):
        started.set()
        for _ in range(100):
            time.sleep(0.05)
        return "x"

    video, stt = _make_manager(tmp_path, slow_transcribe)
    media = tmp_path / "a.mp4"
    media.write_bytes(b"x")
    jid = stt.submit(media, "a.mp4")
    assert started.wait(5)
    assert stt.cancel(jid) is True
    job = _wait_status(stt, jid)
    assert job["status"] == "cancelled"
