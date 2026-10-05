from ...core.adapters import register
from .faster_whisper import FasterWhisper

register("stt", "faster_whisper", FasterWhisper)
