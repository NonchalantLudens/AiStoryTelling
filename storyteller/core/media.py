"""ffmpeg/ffprobe 薄封装；全项目媒体时长读取唯一出口。

可用环境变量 FFMPEG_BIN / FFPROBE_BIN 覆盖二进制路径。
"""
import os
import subprocess
from pathlib import Path


def run_ffmpeg(args: list[str]) -> None:
    cmd = [os.environ.get("FFMPEG_BIN", "ffmpeg"), "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {' '.join(cmd)}\n{proc.stderr}")


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [os.environ.get("FFPROBE_BIN", "ffprobe"),
         "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {proc.stderr}")
    return float(proc.stdout.strip())
