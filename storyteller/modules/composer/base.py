"""合成器接口：把音画片段时间线拼成最终视频。"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class TimelineItem:
    audio: Path
    visual: Path
    text: str = ""
    duration: float = 0.0


class Composer(Protocol):
    name: str

    def compose(
        self,
        timeline: list[TimelineItem],
        out_path: Path,
        srt_text: Optional[str] = None,
    ) -> Path: ...
