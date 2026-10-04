"""任务管理：后台线程跑管线，状态落 outputs/jobs.json。"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .pipeline import PipelineOptions, run_pipeline

PipelineFn = Callable[..., Path]


class JobManager:
    def __init__(
        self,
        config: dict,
        outputs_dir: Path,
        pipeline_fn: PipelineFn = run_pipeline,
    ):
        self.config = config
        self.outputs_dir = Path(outputs_dir)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self._pipeline_fn = pipeline_fn
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._store = self.outputs_dir / "jobs.json"
        self._load()

    # ---- 持久化 ----
    def _load(self) -> None:
        if self._store.exists():
            self._jobs = {
                j["id"]: j
                for j in json.loads(self._store.read_text(encoding="utf-8"))
            }

    def _save(self) -> None:
        with self._lock:
            self._store.write_text(
                json.dumps(list(self._jobs.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

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
        threading.Thread(
            target=self._run, args=(jid, text, overrides or {}), daemon=True
        ).start()
        return jid

    def get(self, job_id: str) -> dict:
        return self._jobs[job_id]

    def list_jobs(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    # ---- 执行 ----
    def _run(self, jid: str, text: str, overrides: dict) -> None:
        job = self._jobs[jid]
        job.update(status="running", stage="init")
        self._save()
        workdir = self.outputs_dir / jid
        workdir.mkdir(parents=True, exist_ok=True)

        def on_progress(stage: str, done: int, total: int) -> None:
            job.update(stage=stage, progress=done, total=total)
            self._save()

        try:
            options = PipelineOptions.from_config(self.config, overrides)
            out = self._pipeline_fn(text, options, workdir, progress=on_progress)
            job.update(status="done", stage="done", output=str(out))
        except Exception as exc:  # 任务线程兜底，失败要可见
            job.update(status="failed", error=str(exc))
        self._save()
