"""图片轮播适配器：assets/loops/<主题>/*.png|jpg 按顺序轮播到指定时长。"""
from pathlib import Path

from ...core.media import run_ffmpeg

_IMAGE_GLOBS = ("*.png", "*.jpg", "*.jpeg")


class StillSlideshow:
    name = "still_slideshow"

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

    def _images(self, theme: str) -> list[Path]:
        def _collect(d: Path) -> list[Path]:
            files: list[Path] = []
            for g in _IMAGE_GLOBS:
                files.extend(d.glob(g))
            return sorted(files)

        files = _collect(self.assets_dir / theme)
        if not files:
            files = _collect(self.assets_dir / self.default_theme)
        if not files:
            raise RuntimeError(f"无可用图片素材：主题 {theme}")
        return files

    def themes(self) -> list[str]:
        if not self.assets_dir.exists():
            return []
        return sorted(
            d.name for d in self.assets_dir.iterdir()
            if d.is_dir() and any(d.glob(g) for g in _IMAGE_GLOBS)
        )

    def resolve(self, theme: str, duration: float, out_path: Path) -> Path:
        images = self._images(theme)
        per = duration / len(images)
        list_file = Path(out_path).with_suffix(".txt")
        lines = []
        for img in images:
            lines.append(f"file '{img.resolve()}'")
            lines.append(f"duration {per:.3f}")
        # concat demuxer 最后一张需重复，否则最后一格时长不生效
        lines.append(f"file '{images[-1].resolve()}'")
        list_file.write_text("\n".join(lines))
        vf = (
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"eq=brightness={self.brightness},fps={self.fps},format=yuv420p"
        )
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-t", f"{duration:.3f}",
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-y", str(out_path),
        ])
        list_file.unlink(missing_ok=True)
        return Path(out_path)
