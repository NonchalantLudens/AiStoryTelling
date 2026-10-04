from ...core.adapters import register
from .edge import EdgeTTS
from .gpt_sovits import GPTSoVITS

register("tts", "edge", EdgeTTS)
register("tts", "gpt_sovits", GPTSoVITS)
