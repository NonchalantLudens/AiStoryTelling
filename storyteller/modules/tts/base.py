"""TTS 适配器接口：给一段文字，产出一个音频文件，返回时长秒。"""
from pathlib import Path
from typing import Protocol


class TTSEngine(Protocol):
    name: str

    def synthesize(self, text: str, out_path: Path) -> float: ...
