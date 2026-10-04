from storyteller.core import adapters
from storyteller.core.pipeline import PipelineOptions, run_pipeline


class FakeTTS:
    name = "fake"

    def __init__(self, **opts):
        self.opts = opts

    def synthesize(self, text: str, out_path) -> float:
        out_path.write_text("wav")
        return _DURATIONS.pop(0)


class FakeVisual:
    name = "fake"

    def __init__(self, **opts):
        self.opts = opts

    def themes(self):
        return ["campfire"]

    def resolve(self, theme: str, duration: float, out_path):
        out_path.write_text("mp4")
        return out_path


class FakeComposer:
    name = "fake"

    def __init__(self, **opts):
        self.opts = opts

    def compose(self, timeline, out_path, srt_text=None):
        total = sum(t.duration for t in timeline)
        out_path.write_text(f"final {total:.2f} {len(timeline)}")
        if srt_text is not None:
            out_path.with_suffix(".srt").write_text(srt_text)
        return out_path


_DURATIONS: list[float] = []

adapters.register("tts", "fake", FakeTTS)
adapters.register("visual", "fake", FakeVisual)
adapters.register("composer", "fake", FakeComposer)


def test_run_pipeline_happy_path(tmp_path):
    _DURATIONS.clear()
    _DURATIONS.extend([1.0, 2.0, 3.5])
    text = "第一段。\n\n第二段是一句比较长的话。它有两句，超过二十字就会一起进这一段。\n\n第三段。"
    opts = PipelineOptions(
        tts_name="fake", visual_name="fake", composer_name="fake",
        embed_srt=True,
    )
    stages: list[tuple] = []
    out = run_pipeline(text, opts, tmp_path, progress=lambda *a: stages.append(a))
    assert out.name == "final.mp4" and out.exists()
    content = out.read_text()
    assert content.startswith("final 6.50 3")
    assert (tmp_path / "final.srt").exists()
    assert (tmp_path / "story_segments.json").exists()
    assert any(s[0] == "tts" for s in stages) and any(s[0] == "done" for s in stages)


def test_options_from_config_and_overrides():
    cfg = {
        "tts": {"name": "edge", "voice": "zh-CN-YunxiNeural", "rate": "+0%"},
        "visual": {"name": "loop_video", "assets_dir": "assets/loops", "default_theme": "campfire"},
        "composer": {"name": "ffmpeg", "bgm": None, "bgm_volume": 0.2, "embed_srt": False},
        "output": {"width": 1280, "height": 720, "fps": 30, "dir": "outputs"},
    }
    o = PipelineOptions.from_config(cfg, overrides={"theme": "rain"})
    assert o.theme == "rain"
    assert o.tts_opts["voice"] == "zh-CN-YunxiNeural"
    assert o.visual_opts["assets_dir"] == "assets/loops"
    assert o.embed_srt is False
