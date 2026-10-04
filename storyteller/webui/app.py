"""FastAPI 后端：提交任务/查询进度/列主题/静态与产物下载。"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import modules as _builtin_modules  # noqa: F401  触发适配器注册
from ..core.adapters import create
from ..core.jobs import JobManager

STATIC_DIR = Path(__file__).parent / "static"


class JobRequest(BaseModel):
    text: str
    overrides: dict | None = None


def create_app(config: dict, outputs_dir: Path) -> FastAPI:
    app = FastAPI(title="Storyteller")
    manager = JobManager(config, Path(outputs_dir))
    app.state.manager = manager

    @app.post("/api/jobs")
    def submit(req: JobRequest):
        if not req.text.strip():
            raise HTTPException(400, "故事文本为空")
        return {"id": manager.submit(req.text, req.overrides)}

    @app.get("/api/jobs")
    def jobs():
        return manager.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        try:
            return manager.get(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在")

    @app.get("/api/themes")
    def themes():
        visual_name = config.get("visual", {}).get("name", "loop_video")
        visual_opts = {
            k: v for k, v in config.get("visual", {}).items() if k != "name"
        }
        visual = create("visual", visual_name, **visual_opts)
        return {
            "themes": visual.themes(),
            "default": config.get("visual", {}).get("default_theme", "campfire"),
        }

    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=outputs_dir), name="outputs")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
