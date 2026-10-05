"""STT 适配器接口：给一个音视频文件，返回转写文本。"""
from pathlib import Path
from typing import Protocol


class STTEngine(Protocol):
    name: str

    def transcribe(self, media_path: Path) -> str: ...
