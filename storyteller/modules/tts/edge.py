"""edge-tts 适配器：零配置兜底，管线联调用。"""
import asyncio
from pathlib import Path

import edge_tts

from ...core.media import probe_duration


class EdgeTTS:
    name = "edge"

    def __init__(self, voice: str = "zh-CN-YunxiNeural", rate: str = "+0%"):
        self.voice = voice
        self.rate = rate

    def synthesize(self, text: str, out_path: Path) -> float:
        out_path = Path(out_path)

        async def _run() -> None:
            comm = edge_tts.Communicate(text, self.voice, rate=self.rate)
            await comm.save(str(out_path))

        asyncio.run(_run())
        return probe_duration(out_path)
