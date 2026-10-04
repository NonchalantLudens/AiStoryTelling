from pathlib import Path

import pytest

from storyteller.core.media import probe_duration, run_ffmpeg
from storyteller.modules.composer.base import TimelineItem

W, H = 320, 180


def _make_segment(tmp_path: Path, i: int, dur: float) -> TimelineItem:
    audio = tmp_path / f"a{i}.wav"
    visual = tmp_path / f"v{i}.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-y", str(audio)])
    run_ffmpeg([
        "-f", "lavfi", "-i", f"color=c=red:size={W}x{H}:duration={dur}",
        "-c:v", "libx264", "-preset", "ultrafast", "-y", str(visual),
    ])
    return TimelineItem(audio=audio, visual=visual, text=f"段{i}", duration=dur)


@pytest.mark.integration
def test_compose_two_segments(tmp_path: Path):
    from storyteller.modules.composer.ffmpeg_composer import FFmpegComposer

    timeline = [_make_segment(tmp_path, 0, 1.0), _make_segment(tmp_path, 1, 1.5)]
    out = tmp_path / "final.mp4"
    c = FFmpegComposer(workdir=tmp_path)
    result = c.compose(timeline, out, srt_text="1\n00:00:00,000 --> 00:00:01,000\n段0")
    assert result == out
    assert 2.3 <= probe_duration(out) <= 2.8
    assert (tmp_path / "final.srt").read_text().startswith("1\n")


@pytest.mark.integration
def test_compose_with_bgm(tmp_path: Path):
    from storyteller.modules.composer.ffmpeg_composer import FFmpegComposer

    timeline = [_make_segment(tmp_path, 0, 1.0)]
    bgm = tmp_path / "bgm.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=220:duration=30", "-y", str(bgm)])
    out = tmp_path / "final.mp4"
    c = FFmpegComposer(bgm=bgm, workdir=tmp_path)
    c.compose(timeline, out)
    assert 0.9 <= probe_duration(out) <= 1.3
