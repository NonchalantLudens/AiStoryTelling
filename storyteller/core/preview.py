"""分步预览：TTS 试听与画面样片，按参数哈希缓存，复用注册表适配器。"""
import hashlib
import json
from pathlib import Path
from typing import Optional

from .adapters import create
from .media import probe_duration


class PreviewManager:
    def __init__(self, config: dict, preview_dir: Path):
        self.config = config
        self.preview_dir = Path(preview_dir)
        self.preview_dir.mkdir(parents=True, exist_ok=True)

    # ---- 内部 ----
    def _cache_path(self, kind: str, key_material: str, ext: str) -> tuple[Path, Path]:
        key = hashlib.md5(key_material.encode()).hexdigest()[:16]
        out = self.preview_dir / f"{kind}_{key}.{ext}"
        return out, out.with_suffix(".json")

    @staticmethod
    def _read_meta(meta: Path) -> Optional[float]:
        if meta.exists():
            try:
                return float(json.loads(meta.read_text())["duration"])
            except (json.JSONDecodeError, KeyError, ValueError):
                return None
        return None

    @staticmethod
    def _write_meta(meta: Path, duration: float) -> None:
        meta.write_text(json.dumps({"duration": duration}))

    # ---- TTS 试听 ----
    def tts(
        self,
        text: str,
        engine: Optional[str] = None,
        tts_opts: Optional[dict] = None,
    ) -> tuple[Path, float]:
        engine = engine or self.config.get("tts", {}).get("name", "edge")
        # 引擎默认参数来自 config.tts（去掉 name），请求参数覆盖
        merged = {
            k: v for k, v in self.config.get("tts", {}).items() if k != "name"
        }
        merged.update(tts_opts or {})
        out, meta = self._cache_path(
            "tts", f"{engine}|{sorted(merged.items())}|{text}",
            "mp3" if engine == "edge" else "wav",
        )
        cached = self._read_meta(meta)
        if out.exists() and cached is not None:
            return out, cached
        adapter = create("tts", engine, **merged)
        duration = float(adapter.synthesize(text, out))
        self._write_meta(meta, duration)
        return out, duration

    # ---- 画面样片 ----
    def visual(
        self,
        theme: str,
        duration: float,
        visual_name: Optional[str] = None,
        visual_opts: Optional[dict] = None,
    ) -> tuple[Path, float]:
        name = visual_name or self.config.get("visual", {}).get("name", "loop_video")
        merged = {
            k: v for k, v in self.config.get("visual", {}).items()
            if k not in ("name", "default_theme")
        }
        o = self.config.get("output", {})
        merged.setdefault("width", o.get("width", 1280))
        merged.setdefault("height", o.get("height", 720))
        merged.setdefault("fps", o.get("fps", 30))
        merged.update(visual_opts or {})
        out, meta = self._cache_path(
            "vis", f"{name}|{sorted(merged.items())}|{theme}|{round(duration, 1)}", "mp4"
        )
        cached = self._read_meta(meta)
        if out.exists() and cached is not None:
            return out, cached
        adapter = create("visual", name, **merged)
        adapter.resolve(theme, duration, out)
        duration = probe_duration(out)
        self._write_meta(meta, duration)
        return out, duration
