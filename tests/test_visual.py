from pathlib import Path

import pytest

from storyteller.core.media import probe_duration, run_ffmpeg

W, H = 320, 180


@pytest.fixture
def loop_asset(tmp_path: Path) -> Path:
    """造一个 1 秒的假循环视频素材（主题 campfire）。"""
    theme_dir = tmp_path / "campfire"
    theme_dir.mkdir()
    src = theme_dir / "a.mp4"
    run_ffmpeg([
        "-f", "lavfi", "-i", f"color=c=orange:size={W}x{H}:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=100:duration=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        "-y", str(src),
    ])
    return tmp_path


@pytest.mark.integration
def test_loop_video_extends_to_duration(loop_asset: Path, tmp_path: Path):
    from storyteller.modules.visual.loop_video import LoopVideo

    v = LoopVideo(assets_dir=loop_asset, width=W, height=H)
    out = tmp_path / "out.mp4"
    result = v.resolve("campfire", 2.5, out)
    assert result == out and out.exists()
    assert 2.4 <= probe_duration(out) <= 2.7


@pytest.mark.integration
def test_loop_video_falls_back_to_default_theme(loop_asset: Path, tmp_path: Path):
    from storyteller.modules.visual.loop_video import LoopVideo

    v = LoopVideo(assets_dir=loop_asset, default_theme="campfire", width=W, height=H)
    out = tmp_path / "out.mp4"
    v.resolve("不存在的主题", 1.5, out)  # 不抛错即回退成功
    assert 1.4 <= probe_duration(out) <= 1.7


@pytest.mark.integration
def test_themes_listing(loop_asset: Path):
    from storyteller.modules.visual.loop_video import LoopVideo

    assert LoopVideo(assets_dir=loop_asset).themes() == ["campfire"]


@pytest.mark.integration
def test_still_slideshow_loops_images(loop_asset: Path, tmp_path: Path):
    from storyteller.modules.visual.still_slideshow import StillSlideshow

    img_dir = tmp_path / "campfire"
    img_dir.mkdir(exist_ok=True)
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c=blue:size={W}x{H}", "-frames:v", "1", "-y", str(img_dir / "p1.png")])
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c=green:size={W}x{H}", "-frames:v", "1", "-y", str(img_dir / "p2.png")])
    s = StillSlideshow(assets_dir=tmp_path, width=W, height=H)
    out = tmp_path / "out.mp4"
    s.resolve("campfire", 3.0, out)
    assert 2.9 <= probe_duration(out) <= 3.2
