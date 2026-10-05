"""STT 任务管理：每个媒体文件一个任务，转写完成后自动入队生成任务。"""
import json
import os
import queue
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .adapters import create
from .jobs import JobManager

TranscribeFn = Callable[[Path], str]
_ACTIVE_STATES = ("queued", "transcribing")


def _default_transcribe_fn(config: dict) -> TranscribeFn:
    def _transcribe(media_path: Path) -> str:
        stt_cfg = config.get("stt", {})
        opts = {k: v for k, v in stt_cfg.items() if k != "name"}
        engine = create("stt", stt_cfg.get("name", "faster_whisper"), **opts)
        return engine.transcribe(media_path)

    return _transcribe


class STTJobManager:
    def __init__(
        self,
        config: dict,
        outputs_dir: Path,
        video_jobs: JobManager,
        transcribe_fn: Optional[TranscribeFn] = None,
        workers: int = 1,
    ):
        self.config = config
        self.outputs_dir = Path(outputs_dir)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self._video_jobs = video_jobs
        self._transcribe_fn = transcribe_fn or _default_transcribe_fn(config)
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._store = self.outputs_dir / "stt_jobs.json"
        self._cancel_flags: set[str] = set()
        self._queue: queue.Queue = queue.Queue()
        self._load()
        self._workers = [
            threading.Thread(target=self._loop, daemon=True, name=f"stt-worker-{i}")
            for i in range(max(1, workers))
        ]
        for w in self._workers:
            w.start()

    # ---- 持久化（原子写，同 JobManager） ----
    def _load(self) -> None:
        if self._store.exists():
            try:
                jobs = json.loads(self._store.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                jobs = []
            for j in jobs:
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
    def submit(
        self,
        media_path: Path,
        filename: str,
        auto_generate: bool = True,
        gen_overrides: Optional[dict] = None,
    ) -> str:
        jid = uuid.uuid4().hex[:12]
        job = {
            "id": jid,
            "filename": filename,
            "path": str(media_path),
            "status": "queued",
            "text": None,
            "gen_job_id": None,
            "auto_generate": auto_generate,
            "gen_overrides": gen_overrides or {},
            "error": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with self._lock:
            self._jobs[jid] = job
        self._save()
        self._queue.put(jid)
        return jid

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job["status"] == "queued":
            job.update(status="cancelled", error="排队时已取消")
            self._save()
            return True
        if job["status"] == "transcribing":
            self._cancel_flags.add(job_id)
            return True
        return False

    def get(self, job_id: str) -> dict:
        return self._jobs[job_id]

    def list_jobs(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    # ---- worker ----
    def _loop(self) -> None:
        while True:
            jid = self._queue.get()
            job = self._jobs.get(jid)
            if job is None or job["status"] == "cancelled":
                continue
            self._run(jid)

    def _run(self, jid: str) -> None:
        job = self._jobs[jid]
        job.update(status="transcribing")
        self._save()

        def cancelled() -> bool:
            return jid in self._cancel_flags

        try:
            if cancelled():
                raise _Cancelled()
            text = self._transcribe_fn(Path(job["path"]))
            if cancelled():
                raise _Cancelled()
            if not text.strip():
                raise RuntimeError("转写结果为空（可能是纯音乐/无语音）")
            job["text"] = text
            if job.get("auto_generate", True):
                job["gen_job_id"] = self._video_jobs.submit(text, job.get("gen_overrides"))
            job.update(status="done")
        except _Cancelled:
            job.update(status="cancelled", error="已取消")
        except Exception as exc:
            job.update(status="failed", error=str(exc))
        finally:
            self._cancel_flags.discard(jid)
            self._save()


class _Cancelled(RuntimeError):
    """内部取消信号。"""
