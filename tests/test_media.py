import pytest

from storyteller.core.media import probe_duration, run_ffmpeg


@pytest.mark.integration
def test_probe_duration_of_1s_tone(tmp_path):
    wav = tmp_path / "tone.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-y", str(wav)])
    assert 0.9 <= probe_duration(wav) <= 1.1


@pytest.mark.integration
def test_run_ffmpeg_raises_on_bad_args(tmp_path):
    with pytest.raises(RuntimeError):
        run_ffmpeg(["-nosuchflag"])
