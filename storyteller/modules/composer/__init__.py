from ...core.adapters import register
from .ffmpeg_composer import FFmpegComposer

register("composer", "ffmpeg", FFmpegComposer)
