from storyteller.core import adapters
from storyteller.core.preview import PreviewManager


class FakeTTS:
    name = "fake"
    calls = 0

    def __init__(self, **opts):
        self.opts = opts

    def synthesize(self, text: str, out_path) -> float:
        FakeTTS.calls += 1
        out_path.write_text(f"audio:{text}")
        return 1.5


def test_tts_preview_cached(tmp_path):
    adapters.register("tts", "cache_tts", FakeTTS)
    FakeTTS.calls = 0
    m = PreviewManager({}, tmp_path)

    p1, d1 = m.tts("你好", engine="cache_tts", tts_opts={"voice": "v1"})
    p2, d2 = m.tts("你好", engine="cache_tts", tts_opts={"voice": "v1"})
    assert p1 == p2 and d1 == d2 == 1.5
    assert FakeTTS.calls == 1  # 同配置第二次命中缓存，不再调用引擎

    p3, _ = m.tts("你好", engine="cache_tts", tts_opts={"voice": "v2"})
    assert p3 != p1  # 配置不同则重新生成
    assert FakeTTS.calls == 2

    p4, _ = m.tts("别的文本", engine="cache_tts", tts_opts={"voice": "v1"})
    assert p4 != p1  # 文本不同也重新生成
