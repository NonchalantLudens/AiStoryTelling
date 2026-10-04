"""分步预览：TTS 试听（按 文本+引擎+配置 哈希缓存），复用注册表适配器。"""
import hashlib
import json
from pathlib import Path
from typing import Optional

from .adapters import create


class PreviewManager:
    def __init__(self, config: dict, preview_dir: Path):
        self.config = config
        self.preview_dir = Path(preview_dir)
        self.preview_dir.mkdir(parents=True, exist_ok=True)

    def tts(
        self,
        text: str,
        engine: Optional[str] = None,
        tts_opts: Optional[dict] = None,
    ) -> tuple[Path, float]:
        """生成/复用试听音频。返回 (音频文件, 时长秒)。"""
        engine = engine or self.config.get("tts", {}).get("name", "edge")
        # 引擎默认参数来自 config.tts（去掉 name），请求参数覆盖
        merged = {
            k: v for k, v in self.config.get("tts", {}).items() if k != "name"
        }
        merged.update(tts_opts or {})
        key = hashlib.md5(
            f"{engine}|{sorted(merged.items())}|{text}".encode()
        ).hexdigest()[:16]
        ext = "mp3" if engine == "edge" else "wav"
        out = self.preview_dir / f"{key}.{ext}"
        meta = out.with_suffix(".json")
        if out.exists() and meta.exists():
            duration = float(json.loads(meta.read_text())["duration"])
            return out, duration
        adapter = create("tts", engine, **merged)
        duration = float(adapter.synthesize(text, out))
        meta.write_text(json.dumps({"duration": duration}))
        return out, duration
