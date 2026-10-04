import time

from storyteller.core.jobs import JobManager


def _fake_pipeline(text, options, workdir, progress=None):
    if progress:
        progress("tts", 1, 1)
        progress("done", 1, 1)
    out = workdir / "final.mp4"
    out.write_text("mp4")
    return out


def _failing_pipeline(text, options, workdir, progress=None):
    raise RuntimeError("TTS 连接失败")


def _wait_status(m, jid):
    for _ in range(200):
        job = m.get(jid)
        if job["status"] in ("done", "failed"):
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
