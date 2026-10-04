from pathlib import Path
from unittest.mock import patch

import pytest

import storyteller.modules.tts  # noqa: F401  触发注册
from storyteller.modules.tts import gpt_sovits as gs
from storyteller.modules.tts.gpt_sovits import GPTSoVITS


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


@pytest.mark.integration
def test_edge_tts_synthesizes(tmp_path: Path):
    from storyteller.modules.tts.edge import EdgeTTS

    engine = EdgeTTS()
    out = tmp_path / "seg.mp3"
    duration = engine.synthesize("你好，这是一个测试。", out)
    assert out.exists() and out.stat().st_size > 0
    assert duration > 0.5


def test_gpt_sovits_posts_params_and_writes_file(tmp_path: Path):
    engine = GPTSoVITS(
        base_url="http://127.0.0.1:9880",
        ref_audio_path="/ref.wav",
        prompt_text="参考文本",
    )
    out = tmp_path / "seg.wav"
    with patch.object(gs.requests, "get", return_value=FakeResponse(b"RIFFDATA")) as m, \
         patch.object(gs, "probe_duration", return_value=1.23):
        duration = engine.synthesize("你好。", out)
    assert out.read_bytes() == b"RIFFDATA"
    assert duration == 1.23
    params = m.call_args.kwargs["params"]
    assert params["text"] == "你好。" and params["text_lang"] == "zh"
    assert params["ref_audio_path"] == "/ref.wav"
