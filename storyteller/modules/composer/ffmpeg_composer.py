"""ffmpeg 合成器：逐段合 mp4 -> concat -> 可选 BGM 混音；srt 写到输出旁。"""
from pathlib import Path
from typing import Optional

from ...core.media import run_ffmpeg
from .base import TimelineItem


class FFmpegComposer:
    name = "ffmpeg"

    def __init__(
        self,
        bgm: Optional[Path] = None,
        bgm_volume: float = 0.2,
        workdir: Optional[Path] = None,
    ):
        self.bgm = Path(bgm) if bgm else None
        self.bgm_volume = bgm_volume
        self.workdir = Path(workdir) if workdir else Path("outputs/_compose")
        self.workdir.mkdir(parents=True, exist_ok=True)

    def compose(
        self,
        timeline: list[TimelineItem],
        out_path: Path,
        srt_text: Optional[str] = None,
    ) -> Path:
        out_path = Path(out_path)
        seg_files: list[Path] = []
        for i, item in enumerate(timeline):
            seg = self.workdir / f"seg_{i:03d}.mp4"
            run_ffmpeg([
                "-i", str(item.visual), "-i", str(item.audio),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-y", str(seg),
            ])
            seg_files.append(seg)

        concat_list = self.workdir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{f.resolve()}'" for f in seg_files)
        )
        merged = self.workdir / "merged.mp4"
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-y", str(merged),
        ])

        if self.bgm:
            mixed = self.workdir / "mixed.mp4"
            run_ffmpeg([
                "-i", str(merged), "-stream_loop", "-1", "-i", str(self.bgm),
                "-filter_complex",
                f"[1:a]volume={self.bgm_volume}[b];[0:a][b]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-y", str(mixed),
            ])
            merged = mixed

        merged.replace(out_path)
        if srt_text is not None:
            out_path.with_suffix(".srt").write_text(srt_text)
        concat_list.unlink(missing_ok=True)
        return out_path
