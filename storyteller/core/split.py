"""把故事文本切成段落片段；每段是一次画面切换的最小单位。"""
import re

_SENT_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def split_text(text: str, max_len: int = 120) -> list[str]:
    segments: list[str] = []
    for para in text.replace("\r\n", "\n").split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_len:
            segments.append(para)
            continue
        current = ""
        for sent in _SENT_RE.findall(para):
            sent = sent.strip()
            if not sent:
                continue
            if current and len(current) + len(sent) > max_len:
                segments.append(current)
                current = sent
            else:
                current = current + sent
        if current:
            segments.append(current)
    return segments
