"""循环视频适配器：免费实拍氛围视频（assets/loops/<主题>/*.mp4）循环到指定时长。"""
import hashlib
from pathlib import Path

from ...core.media import run_ffmpeg


class LoopVideo:
    name = "loop_video"

    def __init__(
        self,
        assets_dir: Path,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        brightness: float = -0.06,
        default_theme: str = "campfire",
    ):
        self.assets_dir = Path(assets_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.brightness = brightness
        self.default_theme = default_theme

    def themes(self) -> list[str]:
        if not self.assets_dir.exists():
            return []
        return sorted(
            d.name for d in self.assets_dir.iterdir()
            if d.is_dir() and any(d.glob("*.mp4"))
        )

    def _pick(self, theme: str) -> Path:
        d = self.assets_dir / theme
        files = sorted(d.glob("*.mp4"))
        if not files:
            d = self.assets_dir / self.default_theme
            files = sorted(d.glob("*.mp4"))
        if not files:
            raise RuntimeError(
                f"无可用画面素材：主题 {theme} 与默认主题均无 mp4（先跑 scripts/fetch_loops.sh）"
            )
        idx = int(hashlib.md5(theme.encode()).hexdigest(), 16) % len(files)
        return files[idx]

    def resolve(self, theme: str, duration: float, out_path: Path) -> Path:
        src = self._pick(theme)
        vf = (
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"eq=brightness={self.brightness},fps={self.fps}"
        )
        run_ffmpeg([
            "-stream_loop", "-1", "-i", str(src),
            "-t", f"{duration:.3f}",
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-y", str(out_path),
        ])
        return Path(out_path)
