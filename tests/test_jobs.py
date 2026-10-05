import json
import threading
import time

from storyteller.core.jobs import JobManager
from storyteller.core.pipeline import PipelineCancelled


def _fake_pipeline(text, options, workdir, progress=None):
    if progress:
        progress("tts", 1, 1)
        progress("done", 1, 1)
    out = workdir / "final.mp4"
    out.write_text("mp4")
    return out


def _failing_pipeline(text, options, workdir, progress=None):
    raise RuntimeError("TTS 连接失败")


def _wait_status(m, jid, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = m.get(jid)
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    return m.get(jid)


def test_submit_run_and_finish(tmp_path):
    m = JobManager({}, tmp_path, pipeline_fn=_fake_pipeline)
    jid = m.submit("一个故事。\n\n第二段。")
    job = _wait_status(m, jid)
    assert job["status"] == "done"
    assert job["output"].endswith("final.mp4")
    assert (tmp_path / jid / "final.mp4").exists()
    assert any(j["id"] == jid for j in m.list_jobs())
    reloaded = JobManager({}, tmp_path, pipeline_fn=_fake_pipeline)
    assert reloaded.get(jid)["status"] == "done"


def test_failure_recorded(tmp_path):
    m = JobManager({}, tmp_path, pipeline_fn=_failing_pipeline)
    jid = m.submit("x")
    job = _wait_status(m, jid)
    assert job["status"] == "failed"
    assert "TTS 连接失败" in job["error"]


def test_jobs_run_in_order(tmp_path):
    """单 worker：两个任务应串行执行。"""
    log = []

    def tracking_pipeline(text, options, workdir, progress=None):
        log.append(("start", text))
        time.sleep(0.2)
        out = workdir / "final.mp4"
        out.write_text("mp4")
        log.append(("end", text))
        return out

    m = JobManager({}, tmp_path, pipeline_fn=tracking_pipeline)
    j1 = m.submit("A")
    j2 = m.submit("B")
    _wait_status(m, j2)
    # 串行：A 的 end 在 B 的 start 之前
    starts = [i for i, e in enumerate(log) if e[0] == "start"]
    ends = [i for i, e in enumerate(log) if e[0] == "end"]
    assert ends[0] < starts[1]


def test_cancel_running(tmp_path):
    started = threading.Event()

    def slow_pipeline(text, options, workdir, progress=None):
        started.set()
        for _ in range(100):
            if options.cancel_check and options.cancel_check():
                raise PipelineCancelled()
            time.sleep(0.05)
        out = workdir / "final.mp4"
        out.write_text("x")
        return out

    m = JobManager({}, tmp_path, pipeline_fn=slow_pipeline)
    jid = m.submit("x")
    assert started.wait(5)
    assert m.cancel(jid) is True
    job = _wait_status(m, jid)
    assert job["status"] == "cancelled"


def test_cancel_queued(tmp_path):
    release = threading.Event()

    def blocker(text, options, workdir, progress=None):
        release.wait(5)
        out = workdir / "final.mp4"
        out.write_text("x")
        return out

    m = JobManager({}, tmp_path, pipeline_fn=blocker)
    j1 = m.submit("a")
    deadline = time.time() + 5
    while m.get(j1)["status"] != "running" and time.time() < deadline:
        time.sleep(0.02)
    j2 = m.submit("b")
    assert m.cancel(j2) is True
    assert m.get(j2)["status"] == "cancelled"
    release.set()


def test_interrupted_on_restart(tmp_path):
    store = tmp_path / "jobs.json"
    store.write_text(json.dumps([
        {"id": "oldrun", "status": "running", "stage": "tts", "progress": 1,
         "total": 3, "error": None, "output": None, "created_at": "2026-01-01T00:00:00"},
        {"id": "oldqueued", "status": "queued", "stage": "", "progress": 0,
         "total": 0, "error": None, "output": None, "created_at": "2026-01-01T00:00:01"},
        {"id": "olddone", "status": "done", "stage": "done", "progress": 1,
         "total": 1, "error": None, "output": "x", "created_at": "2026-01-01T00:00:02"},
    ]), encoding="utf-8")
    m = JobManager({}, tmp_path, pipeline_fn=_fake_pipeline)
    assert m.get("oldrun")["status"] == "interrupted"
    assert m.get("oldqueued")["status"] == "interrupted"
    assert m.get("olddone")["status"] == "done"


def test_cancel_unknown_returns_false(tmp_path):
    m = JobManager({}, tmp_path, pipeline_fn=_fake_pipeline)
    assert m.cancel("nope") is False
