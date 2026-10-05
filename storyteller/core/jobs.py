"""任务管理：单 worker 队列顺序执行，原子落盘，支持取消与中断恢复。"""
import json
import os
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .pipeline import PipelineCancelled, PipelineOptions, run_pipeline

PipelineFn = Callable[..., Path]
_ACTIVE_STATES = ("queued", "running")


class JobManager:
    def __init__(
        self,
        config: dict,
        outputs_dir: Path,
        pipeline_fn: PipelineFn = run_pipeline,
        workers: int = 1,
    ):
        self.config = config
        self.outputs_dir = Path(outputs_dir)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self._pipeline_fn = pipeline_fn
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._store = self.outputs_dir / "jobs.json"
        self._cancel_flags: set[str] = set()
        self._queue: queue.Queue = queue.Queue()
        self._load()
        self._workers = [
            threading.Thread(target=self._loop, daemon=True, name=f"job-worker-{i}")
            for i in range(max(1, workers))
        ]
        for w in self._workers:
            w.start()

    # ---- 持久化（原子写） ----
    def _load(self) -> None:
        if self._store.exists():
            try:
                jobs = json.loads(self._store.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                jobs = []
            for j in jobs:
                # 上次进程退出时还活着的是僵尸任务
                if j.get("status") in _ACTIVE_STATES:
                    j["status"] = "interrupted"
                    j["error"] = "服务重启，任务中断"
                self._jobs[j["id"]] = j
            self._save()

    def _save(self) -> None:
        tmp = self._store.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(
                json.dumps(list(self._jobs.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self._store)

    # ---- 对外接口 ----
    def submit(self, text: str, overrides: Optional[dict] = None) -> str:
        jid = uuid.uuid4().hex[:12]
        job = {
            "id": jid,
            "status": "queued",
            "stage": "",
            "progress": 0,
            "total": 0,
            "error": None,
            "output": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with self._lock:
            self._jobs[jid] = job
        self._save()
        self._queue.put((jid, text, overrides or {}))
        return jid

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job["status"] == "queued":
            job.update(status="cancelled", stage="cancelled", error="排队时已取消")
            self._save()
            return True
        if job["status"] == "running":
            self._cancel_flags.add(job_id)  # 阶段边界生效
            return True
        return False

    def get(self, job_id: str) -> dict:
        return self._jobs[job_id]

    def list_jobs(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    # ---- worker ----
    def _loop(self) -> None:
        while True:
            jid, text, overrides = self._queue.get()
            job = self._jobs.get(jid)
            if job is None or job["status"] == "cancelled":
                continue  # 排队时被取消，直接跳过
            self._run(jid, text, overrides)

    def _run(self, jid: str, text: str, overrides: dict) -> None:
        job = self._jobs[jid]
        job.update(status="running", stage="init")
        self._save()
        workdir = self.outputs_dir / jid
        workdir.mkdir(parents=True, exist_ok=True)

        def on_progress(stage: str, done: int, total: int) -> None:
            if jid in self._cancel_flags:
                raise PipelineCancelled()
            job.update(stage=stage, progress=done, total=total)
            self._save()

        options = PipelineOptions.from_config(self.config, overrides)
        options.cancel_check = lambda: jid in self._cancel_flags
        try:
            out = self._pipeline_fn(text, options, workdir, progress=on_progress)
            job.update(status="done", stage="done", output=str(out))
        except PipelineCancelled:
            job.update(status="cancelled", stage="cancelled", error="已取消")
        except Exception as exc:  # 任务线程兜底，失败要可见
            job.update(status="failed", error=str(exc))
        finally:
            self._cancel_flags.discard(jid)
            self._save()
