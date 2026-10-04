"""管线编排：切分 -> TTS -> 画面 -> 合成。"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..modules.composer.base import TimelineItem
from .adapters import create
from .split import split_text
from .subtitles import build_srt

ProgressFn = Callable[[str, int, int], None]


@dataclass
class PipelineOptions:
    theme: str = "campfire"
    tts_name: str = "edge"
    tts_opts: dict = field(default_factory=dict)
    visual_name: str = "loop_video"
    visual_opts: dict = field(default_factory=dict)
    composer_name: str = "ffmpeg"
    composer_opts: dict = field(default_factory=dict)
    width: int = 1280
    height: int = 720
    fps: int = 30
    bgm: Optional[Path] = None
    embed_srt: bool = True

    @classmethod
    def from_config(
        cls, cfg: dict, overrides: Optional[dict] = None
    ) -> "PipelineOptions":
        o = cfg.get("output", {})
        t = cfg.get("tts", {})
        v = cfg.get("visual", {})
        c = cfg.get("composer", {})
        bgm = c.get("bgm")
        opts = cls(
            theme=v.get("default_theme", "campfire"),
            tts_name=t.get("name", "edge"),
            tts_opts={k: val for k, val in t.items() if k != "name"},
            visual_name=v.get("name", "loop_video"),
            visual_opts={
                k: val for k, val in v.items()
                if k not in ("name", "default_theme")
            },
            composer_name=c.get("name", "ffmpeg"),
            composer_opts={
                k: val for k, val in c.items()
                if k not in ("name", "bgm", "bgm_volume", "embed_srt")
            },
            width=o.get("width", 1280),
            height=o.get("height", 720),
            fps=o.get("fps", 30),
            bgm=Path(bgm) if bgm else None,
            embed_srt=c.get("embed_srt", True),
        )
        opts.composer_opts.setdefault("bgm_volume", c.get("bgm_volume", 0.2))
        if overrides:
            for key, val in overrides.items():
                if hasattr(opts, key):
                    setattr(opts, key, val)
        return opts


def run_pipeline(
    text: str,
    options: PipelineOptions,
    workdir: Path,
    progress: Optional[ProgressFn] = None,
) -> Path:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    report: ProgressFn = progress or (lambda *a: None)

    def _visual_opts() -> dict:
        vo = dict(options.visual_opts)
        vo.setdefault("width", options.width)
        vo.setdefault("height", options.height)
        vo.setdefault("fps", options.fps)
        return vo

    def _composer_opts() -> dict:
        co = dict(options.composer_opts)
        if options.bgm:
            co["bgm"] = options.bgm
        co.setdefault("workdir", workdir / "_compose")
        return co

    tts = create("tts", options.tts_name, **options.tts_opts)
    visual = create("visual", options.visual_name, **_visual_opts())
    composer = create("composer", options.composer_name, **_composer_opts())

    segments = split_text(text)
    if not segments:
        raise ValueError("故事文本为空")
    total = len(segments)
    report("tts", 0, total)

    def _synthesize_with_retry(text: str, audio: Path, attempts: int = 3) -> float:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return tts.synthesize(text, audio)
            except Exception as exc:  # edge-tts 等偶发空响应/网络抖动
                last = exc
                if audio.exists():
                    audio.unlink(missing_ok=True)
                time.sleep(1.0 * (i + 1))
        raise last  # type: ignore[misc]

    timeline: list[TimelineItem] = []
    durations: list[float] = []
    for i, seg in enumerate(segments):
        audio = workdir / f"seg_{i:03d}.mp3"
        duration = _synthesize_with_retry(seg, audio)
        clip = workdir / f"vis_{i:03d}.mp4"
        visual.resolve(options.theme, duration, clip)
        timeline.append(TimelineItem(audio=audio, visual=clip, text=seg, duration=duration))
        durations.append(duration)
        report("tts", i + 1, total)

    report("compose", 0, 1)
    srt_text = build_srt(segments, durations) if options.embed_srt else None
    out = composer.compose(timeline, workdir / "final.mp4", srt_text=srt_text)
    (workdir / "story_segments.json").write_text(
        json.dumps(
            [{"text": s, "duration": d} for s, d in zip(segments, durations)],
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    report("done", 1, 1)
    return out
