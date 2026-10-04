from storyteller.core.subtitles import build_srt


def test_basic_timeline():
    srt = build_srt(["第一句", "第二句"], [2.0, 1.5])
    assert srt == (
        "1\n00:00:00,000 --> 00:00:02,000\n第一句\n\n"
        "2\n00:00:02,000 --> 00:00:03,500\n第二句"
    )
