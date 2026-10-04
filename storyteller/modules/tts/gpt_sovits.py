"""GPT-SoVITS 适配器：对接其 api_v2 HTTP 服务（默认 127.0.0.1:9880）。"""
from pathlib import Path

import requests

from ...core.media import probe_duration


class GPTSoVITS:
    name = "gpt_sovits"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9880",
        ref_audio_path: str = "",
        prompt_text: str = "",
        text_lang: str = "zh",
        prompt_lang: str = "zh",
        timeout: int = 300,
    ):
        self.base_url = base_url.rstrip("/")
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.text_lang = text_lang
        self.prompt_lang = prompt_lang
        self.timeout = timeout

    def synthesize(self, text: str, out_path: Path) -> float:
        out_path = Path(out_path)
        resp = requests.get(
            f"{self.base_url}/tts",
            params={
                "text": text,
                "text_lang": self.text_lang,
                "ref_audio_path": self.ref_audio_path,
                "prompt_text": self.prompt_text,
                "prompt_lang": self.prompt_lang,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return probe_duration(out_path)
