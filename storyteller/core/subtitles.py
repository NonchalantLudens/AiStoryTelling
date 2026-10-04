"""按段落时长生成近似 srt（无词级对齐，够讲故事视频用）。"""


def _fmt(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments: list[str], durations: list[float]) -> str:
    assert len(segments) == len(durations), "段落与时长数量不一致"
    parts: list[str] = []
    t = 0.0
    for i, (text, dur) in enumerate(zip(segments, durations), start=1):
        start, end = t, t + dur
        parts.append(f"{i}\n{_fmt(start)} --> {_fmt(end)}\n{text}")
        t = end
    return "\n\n".join(parts)
