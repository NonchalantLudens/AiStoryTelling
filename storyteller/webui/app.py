"""FastAPI 后端：任务、分步预览、素材管理、静态与产物下载。"""
import re
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import modules as _builtin_modules  # noqa: F401  触发适配器注册
from ..core.adapters import available, create
from ..core.jobs import JobManager
from ..core.preview import PreviewManager
from ..core.split import split_text

STATIC_DIR = Path(__file__).parent / "static"
_MEDIA_EXTS = (".mp4", ".png", ".jpg", ".jpeg")


class JobRequest(BaseModel):
    text: str
    overrides: dict | None = None


class SplitRequest(BaseModel):
    text: str


class TTSPreviewRequest(BaseModel):
    text: str
    engine: str | None = None
    voice: str | None = None
    rate: str | None = None
    ref_audio_path: str | None = None
    prompt_text: str | None = None


def _with_srt(job: dict) -> dict:
    """补充 srt 字段：存在才给路径，避免前端下载到 404 JSON。"""
    data = dict(job)
    out = data.get("output")
    data["srt"] = None
    if out:
        srt = Path(out).with_suffix(".srt")
        if srt.exists():
            data["srt"] = str(srt)
    return data


def _safe_name(name: str) -> str:
    name = Path(name).name
    if not re.fullmatch(r"[\w.-]+", name):
        raise HTTPException(400, "文件名只允许字母数字/-/_/.")
    return name


def _safe_theme(theme: str) -> str:
    """主题名整体校验，禁止任何路径分隔符与 ..。"""
    if not re.fullmatch(r"[\w-]+", theme or ""):
        raise HTTPException(400, "主题名只允许字母数字/-/_")
    return theme


def create_app(config: dict, outputs_dir: Path) -> FastAPI:
    app = FastAPI(title="Storyteller")
    manager = JobManager(config, Path(outputs_dir))
    app.state.manager = manager
    preview = PreviewManager(config, Path(outputs_dir) / "_preview")
    app.state.preview = preview

    assets_dir = Path(config.get("visual", {}).get("assets_dir", "assets/loops"))
    if not assets_dir.is_absolute():
        assets_dir = Path.cwd() / assets_dir
    assets_dir.mkdir(parents=True, exist_ok=True)
    app.state.assets_dir = assets_dir

    # ---- 任务 ----
    @app.post("/api/jobs")
    def submit(req: JobRequest):
        if not req.text.strip():
            raise HTTPException(400, "故事文本为空")
        return {"id": manager.submit(req.text, req.overrides)}

    @app.get("/api/jobs")
    def jobs():
        return [_with_srt(j) for j in manager.list_jobs()]

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        try:
            return _with_srt(manager.get(job_id))
        except KeyError:
            raise HTTPException(404, "任务不存在")

    # ---- 分步预览 ----
    @app.get("/api/engines")
    def engines():
        return {"tts": available("tts"), "visual": available("visual")}

    @app.post("/api/preview/split")
    def preview_split(req: SplitRequest):
        return {"segments": split_text(req.text)}

    @app.post("/api/preview/tts")
    def preview_tts(req: TTSPreviewRequest):
        if not req.text.strip():
            raise HTTPException(400, "文本为空")
        opts: dict = {}
        if req.voice:
            opts["voice"] = req.voice
        if req.rate is not None:
            opts["rate"] = req.rate
        if req.ref_audio_path:
            opts["ref_audio_path"] = req.ref_audio_path
        if req.prompt_text:
            opts["prompt_text"] = req.prompt_text
        try:
            path, duration = preview.tts(req.text, req.engine, opts)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"url": f"/preview/{path.name}", "duration": duration}

    # ---- 素材 ----
    @app.get("/api/assets")
    def assets():
        out: dict[str, list[str]] = {}
        if assets_dir.exists():
            for d in sorted(assets_dir.iterdir()):
                if not d.is_dir():
                    continue
                files = sorted(
                    p.name for p in d.iterdir()
                    if p.suffix.lower() in _MEDIA_EXTS
                )
                if files:
                    out[d.name] = files
        return out

    @app.get("/api/themes")
    def themes():
        return {
            "themes": sorted(assets().keys()),
            "default": config.get("visual", {}).get("default_theme", "night"),
        }

    @app.post("/api/assets/upload")
    async def upload(
        file: UploadFile = File(...),
        theme: str = Form(...),
    ):
        theme = _safe_theme(theme)
        name = _safe_name(file.filename or "asset.mp4")
        target_dir = assets_dir / theme
        target_dir.mkdir(parents=True, exist_ok=True)
        with open(target_dir / name, "wb") as f:
            f.write(await file.read())
        return {"theme": theme, "file": name}

    # ---- 静态资源 ----
    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=outputs_dir), name="outputs")
    app.mount("/preview", StaticFiles(directory=preview.preview_dir), name="preview")
    app.mount("/assets", StaticFiles(directory=assets_dir.parent), name="assets")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
