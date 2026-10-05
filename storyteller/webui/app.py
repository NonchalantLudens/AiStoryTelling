"""FastAPI 后端：任务、分步预览、素材管理、媒体提取、静态与产物下载。"""
import asyncio
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import modules as _builtin_modules  # noqa: F401  触发适配器注册
from ..core.adapters import available, create
from ..core.jobs import JobManager
from ..core.preview import PreviewManager
from ..core.split import split_text
from ..core.stt_jobs import STTJobManager

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


class VisualPreviewRequest(BaseModel):
    theme: str
    duration: float = 3.0


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


# ---- 音色列表（edge-tts，中文） ----
_VOICE_CACHE: list | None = None
_VOICE_FALLBACK = [
    {"short_name": "zh-CN-YunyeNeural", "gender": "男", "desc": "纪录片/历史解说 ★推荐"},
    {"short_name": "zh-CN-YunyangNeural", "gender": "男", "desc": "新闻播报"},
    {"short_name": "zh-CN-YunjianNeural", "gender": "男", "desc": "浑厚解说"},
    {"short_name": "zh-CN-YunxiNeural", "gender": "男", "desc": "自然对话"},
    {"short_name": "zh-CN-YunzeNeural", "gender": "男", "desc": "成熟温暖"},
    {"short_name": "zh-CN-XiaoxiaoNeural", "gender": "女", "desc": "温暖通用"},
    {"short_name": "zh-CN-XiaoyiNeural", "gender": "女", "desc": "活泼明快"},
    {"short_name": "zh-CN-XiaomoNeural", "gender": "女", "desc": "冷静解说"},
    {"short_name": "zh-CN-liaoning-XiaobeiNeural", "gender": "女", "desc": "东北口音"},
    {"short_name": "zh-CN-shaanxi-XiaoniNeural", "gender": "女", "desc": "陕西口音"},
]


def _zh_voices() -> list[dict]:
    global _VOICE_CACHE
    if _VOICE_CACHE is not None:
        return _VOICE_CACHE
    try:
        import edge_tts

        data = edge_tts.list_voices()
        if asyncio.iscoroutine(data):
            data = asyncio.run(data)
        out = []
        for v in data:
            if not v.get("Locale", "").startswith("zh"):
                continue
            tag = v.get("VoiceTag") or {}
            out.append({
                "short_name": v["ShortName"],
                "gender": "男" if v.get("Gender") == "Male" else "女",
                "locale": v.get("Locale", ""),
                "desc": " · ".join(
                    x for x in (tag.get("ContentCategories"), tag.get("VoicePersonalities")) if x
                ),
            })
        if out:
            _VOICE_CACHE = out
            return out
    except Exception:
        pass
    return _VOICE_FALLBACK


def create_app(
    config: dict,
    outputs_dir: Path,
    stt_transcribe_fn=None,
) -> FastAPI:
    app = FastAPI(title="Storyteller")
    manager = JobManager(config, Path(outputs_dir))
    app.state.manager = manager
    stt_manager = STTJobManager(
        config, Path(outputs_dir), manager, transcribe_fn=stt_transcribe_fn
    )
    app.state.stt_manager = stt_manager
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

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        if not manager.cancel(job_id):
            raise HTTPException(400, "任务不存在或当前状态不可取消")
        return {"ok": True}

    # ---- 媒体提取（STT） ----
    @app.post("/api/stt/upload")
    async def stt_upload(
        files: list[UploadFile] = File(...),
        auto_generate: bool = Form(True),
    ):
        upload_dir = Path(outputs_dir) / "stt_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        ids = []
        for f in files:
            name = _safe_name(f.filename or "media.mp4")
            saved = upload_dir / f"{uuid.uuid4().hex[:8]}_{name}"
            with open(saved, "wb") as out:
                out.write(await f.read())
            ids.append({
                "stt_job_id": stt_manager.submit(saved, name, auto_generate=auto_generate),
                "filename": name,
            })
        return {"jobs": ids}

    @app.get("/api/stt/jobs")
    def stt_jobs():
        return stt_manager.list_jobs()

    @app.post("/api/stt/jobs/{job_id}/cancel")
    def stt_cancel(job_id: str):
        if not stt_manager.cancel(job_id):
            raise HTTPException(400, "任务不存在或当前状态不可取消")
        return {"ok": True}

    @app.delete("/api/stt/jobs/{job_id}")
    def stt_delete(job_id: str):
        if not stt_manager.remove(job_id):
            raise HTTPException(400, "任务不存在或转写中不可删除")
        return {"ok": True}

    @app.delete("/api/jobs/{job_id}")
    def job_delete(job_id: str):
        if not manager.remove(job_id):
            raise HTTPException(400, "任务不存在或运行中不可删除")
        return {"ok": True}

    @app.delete("/api/assets/{theme}/{filename}")
    def asset_delete(theme: str, filename: str):
        theme = _safe_theme(theme)
        filename = _safe_name(filename)
        target = assets_dir / theme / filename
        if not target.is_file():
            raise HTTPException(404, "素材不存在")
        target.unlink()
        d = assets_dir / theme
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
        return {"ok": True}

    # ---- 分步预览 ----
    @app.get("/api/engines")
    def engines():
        return {"tts": available("tts"), "visual": available("visual")}

    @app.get("/api/voices")
    def voices():
        return {"voices": _zh_voices()}

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

    @app.post("/api/preview/visual")
    def preview_visual(req: VisualPreviewRequest):
        try:
            path, duration = preview.visual(req.theme, req.duration)
        except (ValueError, RuntimeError) as exc:
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
