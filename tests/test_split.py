from storyteller.core.split import split_text


def test_blank_line_splits_paragraphs():
    text = "第一段内容。\n\n第二段内容。"
    assert split_text(text) == ["第一段内容。", "第二段内容。"]


def test_long_paragraph_split_by_sentence():
    text = "一句话。" * 30  # 120 字
    segs = split_text(text, max_len=50)
    assert all(len(s) <= 60 for s in segs)
    assert "".join(segs).count("一句话。") == 30


def test_empty_and_whitespace_only():
    assert split_text("  \n\n  ") == []


def test_crlf_normalized():
    assert split_text("a。\r\n\r\nb。") == ["a。", "b。"]
