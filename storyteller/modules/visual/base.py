"""画面适配器接口：给主题与时长，产出一段恰好该时长的视频文件。"""
from pathlib import Path
from typing import Protocol


class VisualSource(Protocol):
    name: str

    def resolve(self, theme: str, duration: float, out_path: Path) -> Path: ...

    def themes(self) -> list[str]: ...
