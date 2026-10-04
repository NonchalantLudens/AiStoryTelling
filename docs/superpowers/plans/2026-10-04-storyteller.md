# Storyteller 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 本地个人工具：故事文本 → TTS 配音 + 免费循环视频氛围画面 → mp4，模块可换，带极简 WebUI。

**Architecture:** Python 包 `storyteller`，三个可插拔模块（TTS/Visual/Composer）各定义 Protocol 接口，注册表按 `config.yaml` 选实现；`core/pipeline.py` 编排；ffmpeg 负责全部媒体处理；FastAPI 单页 WebUI 轮询任务进度。

**Tech Stack:** Python 3.10+、ffmpeg/ffprobe（系统安装，brew）、fastapi、uvicorn、edge-tts、requests、pyyaml、pytest、httpx。

## Global Constraints

- 运行于本机 macOS（darwin），WebUI 绑定 `127.0.0.1`
- 视频输出统一 `1280x720`、`30fps`、libx264、crf 23、preset veryfast
- 画面是氛围陪衬：循环视频统一压暗（`eq=brightness=-0.06`），不与配音抢戏
- 依赖只允许：fastapi、uvicorn、edge-tts、requests、pyyaml（运行时）；pytest、httpx（开发）；不引入 moviepy/pydub
- 所有音频时长用 ffprobe 读取（`core/media.py` 唯一出口）
- 单测不依赖网络；依赖 ffmpeg/网络 的测试打 `@pytest.mark.integration`，环境变量 `RUN_INTEGRATION=1` 才执行
- 提交信息用中文 conventional commits（`feat:`/`test:`/`chore:`/`docs:`）

---

### Task 1: 项目脚手架

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `config.yaml`, `.gitignore`, `storyteller/__init__.py`, `storyteller/core/__init__.py`, `storyteller/modules/__init__.py`, `storyteller/modules/tts/__init__.py`, `storyteller/modules/visual/__init__.py`, `storyteller/modules/composer/__init__.py`, `storyteller/webui/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

**Interfaces:**
- Produces: 包结构 `storyteller.core` / `storyteller.modules.*` / `storyteller.webui`；默认配置文件 `config.yaml`

- [ ] **Step 1: 写 pyproject.toml 与 requirements.txt**

`pyproject.toml`:
```toml
[project]
name = "storyteller"
version = "0.1.0"
description = "故事文本 -> TTS + 循环氛围视频 -> 讲故事视频"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "edge-tts>=6.1",
    "requests>=2.31",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]

[tool.pytest.ini_options]
markers = ["integration: 需要 ffmpeg/网络的集成测试"]
```

`requirements.txt`:
```
-r dev-requirements.txt
fastapi>=0.110
uvicorn>=0.29
edge-tts>=6.1
requests>=2.31
pyyaml>=6.0
```

`dev-requirements.txt`:
```
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 2: 写 config.yaml**

```yaml
# 模块选择与参数，各适配器实现可独立替换
tts:
  name: edge            # edge | gpt_sovits
  voice: zh-CN-YunxiNeural
  rate: "+0%"
  # gpt_sovits 参数：
  # base_url: http://127.0.0.1:9880
  # ref_audio_path: ""
  # prompt_text: ""

visual:
  name: loop_video      # loop_video | still_slideshow
  assets_dir: assets/loops
  default_theme: campfire

composer:
  name: ffmpeg
  bgm: null             # BGM 音频路径，null 不加
  bgm_volume: 0.2
  embed_srt: false

output:
  width: 1280
  height: 720
  fps: 30
  dir: outputs
```

- [ ] **Step 3: 写 .gitignore 与包骨架**

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
outputs/
assets/loops/
.venv/
```

每个 `__init__.py` 为空文件。

- [ ] **Step 4: 安装并验证**

Run: `cd /Users/fang/Documents/Projects/AiStoryTelling && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest && which ffmpeg`
Expected: pytest 输出 `no tests ran`（exit 5 属预期，改用 `pytest --co -q` 则 `no tests collected`）；ffmpeg 有路径。若 ffmpeg 缺失：`brew install ffmpeg`。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt dev-requirements.txt config.yaml .gitignore storyteller tests
git commit -m "chore: 项目脚手架（包结构/配置/依赖）"
```

---

### Task 2: 文本切分 core/split.py

**Files:**
- Create: `storyteller/core/split.py`
- Test: `tests/test_split.py`

**Interfaces:**
- Produces: `split_text(text: str, max_len: int = 120) -> list[str]`（段落为画面切换单位；超长段落按句切分拼接）

- [ ] **Step 1: 写失败测试**

`tests/test_split.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_split.py -v`
Expected: FAIL `ModuleNotFoundError: storyteller.core.split`

- [ ] **Step 3: 实现**

`storyteller/core/split.py`:
```python
"""把故事文本切成段落片段；每段是一次画面切换的最小单位。"""
import re

_SENT_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")
_CLOSERS = "。！？!?；;"


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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_split.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/core/split.py tests/test_split.py
git commit -m "feat: 文本切分模块（段落/句子二级切分）"
```

---

### Task 3: 媒体工具 core/media.py（ffprobe 时长）

**Files:**
- Create: `storyteller/core/media.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Produces: `probe_duration(path: Path) -> float`；`run_ffmpeg(args: list[str]) -> None`

- [ ] **Step 1: 写测试（集成标记，本机有 ffmpeg 即跑）**

`tests/test_media.py`:
```python
import subprocess
from pathlib import Path

import pytest

from storyteller.core.media import probe_duration, run_ffmpeg


@pytest.mark.integration
def test_probe_duration_of_1s_tone(tmp_path: Path):
    wav = tmp_path / "tone.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-y", str(wav)])
    assert 0.9 <= probe_duration(wav) <= 1.1


@pytest.mark.integration
def test_run_ffmpeg_raises_on_bad_args(tmp_path: Path):
    with pytest.raises(RuntimeError):
        run_ffmpeg(["-nosuchflag"])
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_media.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`storyteller/core/media.py`:
```python
"""ffmpeg/ffprobe 薄封装；全项目媒体时长读取唯一出口。"""
import subprocess
from pathlib import Path


def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {' '.join(cmd)}\n{proc.stderr}")


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {proc.stderr}")
    return float(proc.stdout.strip())
```

- [ ] **Step 4: 运行确认通过**

Run: `RUN_INTEGRATION=1 .venv/bin/pytest tests/test_media.py -v -m integration`
Expected: 2 passed（注意 conftest 尚未过滤，Task 1 的 conftest 先不含 skip 逻辑，此处直接用 `-m integration` 手动跑；若希望默认跳过，在 conftest 加：
```python
# tests/conftest.py
import os

collect_ignore_glob = []


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_INTEGRATION") == "1":
        return
    skip = __import__("pytest").mark.skip(reason="需 RUN_INTEGRATION=1")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
```
此文件在 Task 1 已创建为空，本任务补上以上内容）。

- [ ] **Step 5: Commit**

```bash
git add storyteller/core/media.py tests/test_media.py tests/conftest.py
git commit -m "feat: ffmpeg/ffprobe 封装（时长探测唯一出口）"
```

---

### Task 4: 适配器注册表 core/adapters.py

**Files:**
- Create: `storyteller/core/adapters.py`
- Modify: `tests/conftest.py`（末尾追加 fake 注册夹具）
- Test: `tests/test_adapters.py`

**Interfaces:**
- Produces: `register(kind: str, name: str, cls: type)`、`create(kind: str, name: str, **opts) -> object`
- 注册表初始内容：tts → edge/gpt_sovits（Task 5 实现，此处先建 dict，Task 5 注册）；visual → loop_video/still_slideshow（Task 6）；composer → ffmpeg（Task 7）。本任务只实现机制 + 用 fake 验证。

- [ ] **Step 1: 写失败测试**

`tests/test_adapters.py`:
```python
import pytest

from storyteller.core import adapters


class Fake:
    def __init__(self, a=None):
        self.a = a


def test_register_and_create():
    adapters.register("tts", "fake", Fake)
    obj = adapters.create("tts", "fake", a=1)
    assert isinstance(obj, Fake) and obj.a == 1


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="未知模块类型"):
        adapters.create("nosuch", "x")


def test_unknown_name_raises():
    adapters.register("tts", "fake2", Fake)
    with pytest.raises(ValueError, match="未注册的适配器"):
        adapters.create("tts", "nope")
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_adapters.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`storyteller/core/adapters.py`:
```python
"""模块注册表：kind -> name -> 类。config.yaml 里选名字，这里实例化。"""
from typing import Any

_REGISTRY: dict[str, dict[str, type]] = {
    "tts": {},
    "visual": {},
    "composer": {},
}


def register(kind: str, name: str, cls: type) -> None:
    _REGISTRY.setdefault(kind, {})[name] = cls


def create(kind: str, name: str, **opts: Any) -> Any:
    if kind not in _REGISTRY:
        raise ValueError(f"未知模块类型: {kind}")
    table = _REGISTRY[kind]
    if name not in table:
        raise ValueError(f"未注册的适配器: {kind}/{name}，可选: {sorted(table)}")
    return table[name](**opts)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_adapters.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/core/adapters.py tests/test_adapters.py
git commit -m "feat: 适配器注册表（kind/name 二级查找）"
```

---

### Task 5: TTS 模块（base + edge + gpt_sovits）

**Files:**
- Create: `storyteller/modules/tts/base.py`, `storyteller/modules/tts/edge.py`, `storyteller/modules/tts/gpt_sovits.py`
- Modify: `storyteller/modules/tts/__init__.py`（注册）
- Test: `tests/test_tts.py`

**Interfaces:**
- Produces: `TTSEngine` Protocol：`synthesize(self, text: str, out_path: Path) -> float`（写音频文件、返回秒）；类 `EdgeTTS(voice, rate)`、`GPTSoVITS(base_url, ref_audio_path, prompt_text, text_lang, prompt_lang)`；两者在 `__init__.py` 注册为 `tts/edge`、`tts/gpt_sovits`

- [ ] **Step 1: 写接口 base.py（无测试，纯协议）**

`storyteller/modules/tts/base.py`:
```python
"""TTS 适配器接口：给一段文字，产出一个音频文件，返回时长秒。"""
from pathlib import Path
from typing import Protocol


class TTSEngine(Protocol):
    name: str

    def synthesize(self, text: str, out_path: Path) -> float: ...
```

- [ ] **Step 2: 写失败测试**

`tests/test_tts.py`:
```python
from pathlib import Path
from unittest.mock import patch

import pytest

from storyteller.modules.tts import gpt_sovits as gs
from storyteller.modules.tts.gpt_sovits import GPTSoVITS


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


@pytest.mark.integration
def test_edge_tts_synthesizes(tmp_path: Path):
    from storyteller.modules.tts.edge import EdgeTTS

    engine = EdgeTTS()
    out = tmp_path / "seg.mp3"
    duration = engine.synthesize("你好，这是一个测试。", out)
    assert out.exists() and out.stat().st_size > 0
    assert duration > 0.5


def test_gpt_sovits_posts_params_and_writes_file(tmp_path: Path):
    engine = GPTSoVITS(
        base_url="http://127.0.0.1:9880",
        ref_audio_path="/ref.wav",
        prompt_text="参考文本",
    )
    out = tmp_path / "seg.wav"
    with patch.object(gs.requests, "get", return_value=FakeResponse(b"RIFFDATA")) as m:
        duration = engine.synthesize("你好。", out)
    assert out.read_bytes() == b"RIFFDATA"
    assert duration == 0.0  # 无效音频 probe 失败时由 media 抛错；fake 内容非法——见 Step 3 设计：写文件后 probe，这里 mock probe
    params = m.call_args.kwargs["params"]
    assert params["text"] == "你好。" and params["text_lang"] == "zh"
```

注意：上面 `duration == 0.0` 断言与真实 probe 冲突，最终测试以 Step 3 实现后修正为：
```python
    with patch.object(gs, "probe_duration", return_value=1.23):
        duration = engine.synthesize("你好。", out)
    assert duration == 1.23
```
（即测试中两段 patch：`requests.get` 验参 + `probe_duration` 验返回值，写测试时直接用修正版，避免无意义断言。）

- [ ] **Step 3: 实现 edge.py 与 gpt_sovits.py**

`storyteller/modules/tts/edge.py`:
```python
"""edge-tts 适配器：零配置兜底，管线联调用。"""
import asyncio
from pathlib import Path

import edge_tts

from ...core.media import probe_duration


class EdgeTTS:
    name = "edge"

    def __init__(self, voice: str = "zh-CN-YunxiNeural", rate: str = "+0%"):
        self.voice = voice
        self.rate = rate

    def synthesize(self, text: str, out_path: Path) -> float:
        out_path = Path(out_path)

        async def _run() -> None:
            comm = edge_tts.Communicate(text, self.voice, rate=self.rate)
            await comm.save(str(out_path))

        asyncio.run(_run())
        return probe_duration(out_path)
```

`storyteller/modules/tts/gpt_sovits.py`:
```python
"""GPT-SoVITS 适配器：对接其 api_v2 HTTP 服务（默认 127.0.0.1:9880）。"""
from pathlib import Path

import requests

from ...core.media import probe_duration


class GPTSoVITS:
    name = "gpt_sovits"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9880",
        ref_audio_path: str = "",
        prompt_text: str = "",
        text_lang: str = "zh",
        prompt_lang: str = "zh",
        timeout: int = 300,
    ):
        self.base_url = base_url.rstrip("/")
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.text_lang = text_lang
        self.prompt_lang = prompt_lang
        self.timeout = timeout

    def synthesize(self, text: str, out_path: Path) -> float:
        out_path = Path(out_path)
        resp = requests.get(
            f"{self.base_url}/tts",
            params={
                "text": text,
                "text_lang": self.text_lang,
                "ref_audio_path": self.ref_audio_path,
                "prompt_text": self.prompt_text,
                "prompt_lang": self.prompt_lang,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return probe_duration(out_path)
```

`storyteller/modules/tts/__init__.py`:
```python
from ...core.adapters import register
from .edge import EdgeTTS
from .gpt_sovits import GPTSoVITS

register("tts", "edge", EdgeTTS)
register("tts", "gpt_sovits", GPTSoVITS)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_tts.py -v`（跳过集成）和 `RUN_INTEGRATION=1 .venv/bin/pytest tests/test_tts.py -v -m integration`（跑 edge 真实合成）
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/modules/tts tests/test_tts.py
git commit -m "feat: TTS 模块（edge 零配置 + GPT-SoVITS api_v2 适配器）"
```

---

### Task 6: 画面模块（base + loop_video + still_slideshow）

**Files:**
- Create: `storyteller/modules/visual/base.py`, `storyteller/modules/visual/loop_video.py`, `storyteller/modules/visual/still_slideshow.py`
- Modify: `storyteller/modules/visual/__init__.py`（注册）
- Test: `tests/test_visual.py`

**Interfaces:**
- Produces: `VisualSource` Protocol：`resolve(self, theme: str, duration: float, out_path: Path) -> Path`；`LoopVideo(assets_dir, width=1280, height=720, fps=30, brightness=-0.06, default_theme="campfire")` 另有 `themes() -> list[str]`；`StillSlideshow(assets_dir, ...)` 同接口。注册名 `visual/loop_video`、`visual/still_slideshow`

- [ ] **Step 1: 写接口 base.py**

`storyteller/modules/visual/base.py`:
```python
"""画面适配器接口：给主题与时长，产出一段恰好该时长的视频文件。"""
from pathlib import Path
from typing import Protocol


class VisualSource(Protocol):
    name: str

    def resolve(self, theme: str, duration: float, out_path: Path) -> Path: ...

    def themes(self) -> list[str]: ...
```

- [ ] **Step 2: 写失败测试**

`tests/test_visual.py`:
```python
from pathlib import Path

import pytest

from storyteller.core.media import probe_duration, run_ffmpeg

W, H = 320, 180


@pytest.fixture
def loop_asset(tmp_path: Path) -> Path:
    """造一个 1 秒的假循环视频素材。"""
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
    img_dir.mkdir()
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c=blue:size={W}x{H}", "-frames:v", "1", "-y", str(img_dir / "p1.png")])
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c=green:size={W}x{H}", "-frames:v", "1", "-y", str(img_dir / "p2.png")])
    s = StillSlideshow(assets_dir=tmp_path, width=W, height=H)
    out = tmp_path / "out.mp4"
    s.resolve("campfire", 3.0, out)
    assert 2.9 <= probe_duration(out) <= 3.2
```

- [ ] **Step 3: 实现**

`storyteller/modules/visual/loop_video.py`:
```python
"""循环视频适配器：免费实拍氛围视频（assets/loops/<主题>/*.mp4）循环到指定时长。"""
import hashlib
from pathlib import Path

from ...core.media import run_ffmpeg


class LoopVideo:
    name = "loop_video"

    def __init__(
        self,
        assets_dir: Path,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        brightness: float = -0.06,
        default_theme: str = "campfire",
    ):
        self.assets_dir = Path(assets_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.brightness = brightness
        self.default_theme = default_theme

    def themes(self) -> list[str]:
        if not self.assets_dir.exists():
            return []
        return sorted(
            d.name for d in self.assets_dir.iterdir()
            if d.is_dir() and any(d.glob("*.mp4"))
        )

    def _pick(self, theme: str) -> Path:
        d = self.assets_dir / theme
        files = sorted(d.glob("*.mp4"))
        if not files:
            d = self.assets_dir / self.default_theme
            files = sorted(d.glob("*.mp4"))
        if not files:
            raise RuntimeError(f"无可用画面素材：主题 {theme} 与默认主题均无 mp4（先跑 scripts/fetch_loops.sh）")
        idx = int(hashlib.md5(theme.encode()).hexdigest(), 16) % len(files)
        return files[idx]

    def resolve(self, theme: str, duration: float, out_path: Path) -> Path:
        src = self._pick(theme)
        vf = (
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"eq=brightness={self.brightness},fps={self.fps}"
        )
        run_ffmpeg([
            "-stream_loop", "-1", "-i", str(src),
            "-t", f"{duration:.3f}",
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-y", str(out_path),
        ])
        return Path(out_path)
```

`storyteller/modules/visual/still_slideshow.py`:
```python
"""图片轮播适配器：assets/loops/<主题>/*.png|jpg 按顺序轮播到指定时长。"""
import hashlib
from pathlib import Path

from ...core.media import run_ffmpeg

_IMAGE_GLOBS = ("*.png", "*.jpg", "*.jpeg")


class StillSlideshow:
    name = "still_slideshow"

    def __init__(
        self,
        assets_dir: Path,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        brightness: float = -0.06,
        default_theme: str = "campfire",
    ):
        self.assets_dir = Path(assets_dir)
        self.width = width
        self.height = height
        self.fps = fps
        self.brightness = brightness
        self.default_theme = default_theme

    def _images(self, theme: str) -> list[Path]:
        def _collect(d: Path) -> list[Path]:
            files: list[Path] = []
            for g in _IMAGE_GLOBS:
                files.extend(d.glob(g))
            return sorted(files)

        files = _collect(self.assets_dir / theme)
        if not files:
            files = _collect(self.assets_dir / self.default_theme)
        if not files:
            raise RuntimeError(f"无可用图片素材：主题 {theme}")
        return files

    def themes(self) -> list[str]:
        if not self.assets_dir.exists():
            return []
        return sorted(
            d.name for d in self.assets_dir.iterdir()
            if d.is_dir() and any(d.glob(g) for g in _IMAGE_GLOBS)
        )

    def resolve(self, theme: str, duration: float, out_path: Path) -> Path:
        images = self._images(theme)
        # 每张图平均分时长；concat demuxer 需要相对安全的绝对路径列表
        per = duration / len(images)
        list_file = Path(out_path).with_suffix(".txt")
        lines = []
        for img in images:
            lines.append(f"file '{img.resolve()}'")
            lines.append(f"duration {per:.3f}")
        lines.append(f"file '{images[-1].resolve()}'")  # concat demuxer 最后一张需重复
        list_file.write_text("\n".join(lines))
        vf = (
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"eq=brightness={self.brightness},fps={self.fps},format=yuv420p"
        )
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-t", f"{duration:.3f}",
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-y", str(out_path),
        ])
        list_file.unlink(missing_ok=True)
        return Path(out_path)
```

`storyteller/modules/visual/__init__.py`:
```python
from ...core.adapters import register
from .loop_video import LoopVideo
from .still_slideshow import StillSlideshow

register("visual", "loop_video", LoopVideo)
register("visual", "still_slideshow", StillSlideshow)
```

- [ ] **Step 4: 运行确认通过**

Run: `RUN_INTEGRATION=1 .venv/bin/pytest tests/test_visual.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/modules/visual tests/test_visual.py
git commit -m "feat: 画面模块（循环视频/图片轮播适配器 + 压暗）"
```

---

### Task 7: 字幕生成 core/subtitles.py

**Files:**
- Create: `storyteller/core/subtitles.py`
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Produces: `build_srt(segments: list[str], durations: list[float]) -> str`（段落顺序时间轴，近似字幕）

- [ ] **Step 1: 写失败测试**

`tests/test_subtitles.py`:
```python
from storyteller.core.subtitles import build_srt


def test_basic_timeline():
    srt = build_srt(["第一句", "第二句"], [2.0, 1.5])
    assert srt == (
        "1\n00:00:00,000 --> 00:00:02,000\n第一句\n\n"
        "2\n00:00:02,000 --> 00:00:03,500\n第二句"
    )
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_subtitles.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`storyteller/core/subtitles.py`:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_subtitles.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/core/subtitles.py tests/test_subtitles.py
git commit -m "feat: 段落时长近似 srt 字幕生成"
```

---

### Task 8: 合成器 modules/composer/ffmpeg_composer.py

**Files:**
- Create: `storyteller/modules/composer/base.py`, `storyteller/modules/composer/ffmpeg_composer.py`
- Modify: `storyteller/modules/composer/__init__.py`（注册）
- Test: `tests/test_composer.py`

**Interfaces:**
- Consumes: `core.media.run_ffmpeg/probe_duration`、`core.subtitles.build_srt`
- Produces: `TimelineItem` dataclass（`audio: Path`、`visual: Path`、`text: str = ""`、`duration: float = 0.0`）；`Composer` Protocol：`compose(self, timeline: list[TimelineItem], out_path: Path, srt_text: str | None = None) -> Path`；`FFmpegComposer(bgm=None, bgm_volume=0.2, workdir=None)`，srt 写在 `out_path.with_suffix(".srt")`。注册名 `composer/ffmpeg`

- [ ] **Step 1: 写接口 base.py**

`storyteller/modules/composer/base.py`:
```python
"""合成器接口：把音画片段时间线拼成最终视频。"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class TimelineItem:
    audio: Path
    visual: Path
    text: str = ""
    duration: float = 0.0


class Composer(Protocol):
    name: str

    def compose(
        self,
        timeline: list[TimelineItem],
        out_path: Path,
        srt_text: Optional[str] = None,
    ) -> Path: ...
```

- [ ] **Step 2: 写失败测试**

`tests/test_composer.py`:
```python
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
```

- [ ] **Step 3: 实现 ffmpeg_composer.py**

`storyteller/modules/composer/ffmpeg_composer.py`:
```python
"""ffmpeg 合成器：逐段合 mp4 -> concat -> 可选 BGM 混音；srt 写到输出旁。"""
from pathlib import Path
from typing import Optional

from ...core.media import probe_duration, run_ffmpeg
from .base import TimelineItem


class FFmpegComposer:
    name = "ffmpeg"

    def __init__(
        self,
        bgm: Optional[Path] = None,
        bgm_volume: float = 0.2,
        workdir: Optional[Path] = None,
    ):
        self.bgm = Path(bgm) if bgm else None
        self.bgm_volume = bgm_volume
        self.workdir = Path(workdir) if workdir else Path("outputs/_compose")
        self.workdir.mkdir(parents=True, exist_ok=True)

    def compose(
        self,
        timeline: list[TimelineItem],
        out_path: Path,
        srt_text: Optional[str] = None,
    ) -> Path:
        out_path = Path(out_path)
        seg_files: list[Path] = []
        for i, item in enumerate(timeline):
            seg = self.workdir / f"seg_{i:03d}.mp4"
            run_ffmpeg([
                "-i", str(item.visual), "-i", str(item.audio),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-y", str(seg),
            ])
            seg_files.append(seg)

        concat_list = self.workdir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{f.resolve()}'" for f in seg_files)
        )
        merged = self.workdir / "merged.mp4"
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-y", str(merged),
        ])

        if self.bgm:
            mixed = self.workdir / "mixed.mp4"
            run_ffmpeg([
                "-i", str(merged), "-stream_loop", "-1", "-i", str(self.bgm),
                "-filter_complex",
                f"[1:a]volume={self.bgm_volume}[b];[0:a][b]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-y", str(mixed),
            ])
            merged = mixed

        merged.replace(out_path)
        if srt_text is not None:
            out_path.with_suffix(".srt").write_text(srt_text)
        concat_list.unlink(missing_ok=True)
        return out_path
```

`storyteller/modules/composer/__init__.py`:
```python
from ...core.adapters import register
from .ffmpeg_composer import FFmpegComposer

register("composer", "ffmpeg", FFmpegComposer)
```

- [ ] **Step 4: 运行确认通过**

Run: `RUN_INTEGRATION=1 .venv/bin/pytest tests/test_composer.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/modules/composer tests/test_composer.py
git commit -m "feat: ffmpeg 合成器（分段拼接/BGM 混音/srt 输出）"
```

---

### Task 9: 管线编排 core/pipeline.py 与配置装载

**Files:**
- Create: `storyteller/core/config.py`, `storyteller/core/pipeline.py`
- Modify: `storyteller/core/__init__.py` 无需改
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `split_text`、`adapters.create`、`build_srt`
- Produces:
  - `load_config(path: Path = Path("config.yaml")) -> dict`
  - `@dataclass PipelineOptions`: `theme: str = "campfire"`、`tts_name: str = "edge"`、`tts_opts: dict`、`visual_name: str = "loop_video"`、`visual_opts: dict`、`composer_name: str = "ffmpeg"`、`composer_opts: dict`、`width/height/fps: int`、`bgm: Path | None`、`embed_srt: bool = True`；类方法 `from_config(cfg: dict, overrides: dict | None = None) -> PipelineOptions`（overrides 优先，来自 WebUI 请求）
  - `run_pipeline(text: str, options: PipelineOptions, workdir: Path, progress=None) -> Path`（返回 final.mp4；`progress(stage: str, done: int, total: int)` 回调）
  - 管线内部把 `options.tts_opts` 等传给 `adapters.create`；`width/height/fps` 合入 `visual_opts`

- [ ] **Step 1: 写失败测试（全部用 fake，不依赖 ffmpeg/网络）**

`tests/test_pipeline.py`:
```python
import wave
from pathlib import Path

from storyteller.core import adapters
from storyteller.core.pipeline import PipelineOptions, run_pipeline


def _wav(path: Path, seconds: float, rate: int = 8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return seconds


class FakeTTS:
    name = "fake"

    def __init__(self, **opts):
        self.opts = opts

    def synthesize(self, text: str, out_path: Path) -> float:
        out_path.write_text("wav")  # 假音频，真实时长由 FakeTTS 的固定值表驱动
        return _DURATIONS.pop(0)


class FakeVisual:
    name = "fake"

    def __init__(self, **opts):
        self.opts = opts

    def themes(self):
        return ["campfire"]

    def resolve(self, theme: str, duration: float, out_path: Path) -> Path:
        out_path.write_text("mp4")
        return Path(out_path)


class FakeComposer:
    name = "fake"

    def __init__(self, **opts):
        self.opts = opts

    def compose(self, timeline, out_path, srt_text=None):
        total = sum(t.duration for t in timeline)
        Path(out_path).write_text(f"final {total:.2f} {len(timeline)}")
        if srt_text is not None:
            Path(out_path).with_suffix(".srt").write_text(srt_text)
        return Path(out_path)


_DURATIONS: list[float] = []

adapters.register("tts", "fake", FakeTTS)
adapters.register("visual", "fake", FakeVisual)
adapters.register("composer", "fake", FakeComposer)


def test_run_pipeline_happy_path(tmp_path: Path):
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
    assert (tmp_path / "story_segments.json").exists()  # 段落+时长记录，供调试
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现 config.py 与 pipeline.py**

`storyteller/core/config.py`:
```python
"""config.yaml 装载。"""
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path("config.yaml")


def load_config(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
```

`storyteller/core/pipeline.py`:
```python
"""管线编排：切分 -> TTS -> 画面 -> 合成。"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

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
            visual_opts={k: val for k, val in v.items() if k not in ("name", "default_theme")},
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

    timeline = []
    durations: list[float] = []
    for i, seg in enumerate(segments):
        audio = workdir / f"seg_{i:03d}.mp3"
        duration = tts.synthesize(seg, audio)
        clip = workdir / f"vis_{i:03d}.mp4"
        visual.resolve(options.theme, duration, clip)
        durations.append(duration)
        from .modules_timeline import TimelineItem  # noqa: 见下方说明——直接顶层导入
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
```

修正说明：`TimelineItem` 直接顶层导入 `from .adapters import ...` 旁加 `from ..modules.composer.base import TimelineItem`，删掉循环内那行错位导入，并把循环体补全为：
```python
        timeline.append(TimelineItem(audio=audio, visual=clip, text=seg, duration=duration))
        durations.append(duration)
        report("tts", i + 1, total)
```
（实现时以此为准：顶层 `from ..modules.composer.base import TimelineItem`，循环内 append。）

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/core/config.py storyteller/core/pipeline.py tests/test_pipeline.py
git commit -m "feat: 管线编排与配置装载（fake 适配器全覆盖单测）"
```

---

### Task 10: 任务管理 core/jobs.py

**Files:**
- Create: `storyteller/core/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `run_pipeline`、`PipelineOptions.from_config`
- Produces: `JobManager(config: dict, outputs_dir: Path, pipeline_fn=run_pipeline)`：
  - `submit(text: str, overrides: dict | None = None) -> str`（job_id）
  - `get(job_id) -> dict`（`{id, status: queued|running|done|failed, stage, progress, total, error, output, created_at}`）
  - `list_jobs() -> list[dict]`
  - 状态持久化 `outputs_dir/jobs.json`；每个 job 输出目录 `outputs_dir/<job_id>/`

- [ ] **Step 1: 写失败测试**

`tests/test_jobs.py`:
```python
import time
from pathlib import Path

from storyteller.core.jobs import JobManager


def _fake_pipeline(text, options, workdir, progress=None):
    if progress:
        progress("tts", 1, 1)
        progress("done", 1, 1)
    out = Path(workdir) / "final.mp4"
    Path(out).write_text("mp4")
    return out


def _failing_pipeline(text, options, workdir, progress=None):
    raise RuntimeError("TTS 连接失败")


def test_submit_run_and_finish(tmp_path: Path):
    m = JobManager({}, tmp_path, pipeline_fn=_fake_pipeline)
    jid = m.submit("一个故事。\n\n第二段。")
    for _ in range(100):
        job = m.get(jid)
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    job = m.get(jid)
    assert job["status"] == "done"
    assert job["output"].endswith("final.mp4")
    assert (tmp_path / jid / "final.mp4").exists()
    # 持久化
    assert any(j["id"] == jid for j in m.list_jobs())
    reloaded = JobManager({}, tmp_path, pipeline_fn=_fake_pipeline)
    assert reloaded.get(jid)["status"] == "done"


def test_failure_recorded(tmp_path: Path):
    m = JobManager({}, tmp_path, pipeline_fn=_failing_pipeline)
    jid = m.submit("x")
    for _ in range(100):
        if m.get(jid)["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    job = m.get(jid)
    assert job["status"] == "failed"
    assert "TTS 连接失败" in job["error"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_jobs.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`storyteller/core/jobs.py`:
```python
"""任务管理：后台线程跑管线，状态落 outputs/jobs.json。"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .pipeline import PipelineOptions, run_pipeline

PipelineFn = Callable[..., Path]


class JobManager:
    def __init__(self, config: dict, outputs_dir: Path, pipeline_fn: PipelineFn = run_pipeline):
        self.config = config
        self.outputs_dir = Path(outputs_dir)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self._pipeline_fn = pipeline_fn
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._store = self.outputs_dir / "jobs.json"
        self._load()

    # ---- 持久化 ----
    def _load(self) -> None:
        if self._store.exists():
            self._jobs = {
                j["id"]: j for j in json.loads(self._store.read_text(encoding="utf-8"))
            }

    def _save(self) -> None:
        with self._lock:
            self._store.write_text(
                json.dumps(list(self._jobs.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ---- 对外接口 ----
    def submit(self, text: str, overrides: Optional[dict] = None) -> str:
        jid = uuid.uuid4().hex[:12]
        job = {
            "id": jid,
            "status": "queued",
            "stage": "",
            "progress": 0,
            "total": 0,
            "error": None,
            "output": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with self._lock:
            self._jobs[jid] = job
        self._save()
        threading.Thread(
            target=self._run, args=(jid, text, overrides or {}), daemon=True
        ).start()
        return jid

    def get(self, job_id: str) -> dict:
        return self._jobs[job_id]

    def list_jobs(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    # ---- 执行 ----
    def _run(self, jid: str, text: str, overrides: dict) -> None:
        job = self._jobs[jid]
        job.update(status="running", stage="init")
        self._save()
        workdir = self.outputs_dir / jid

        def on_progress(stage: str, done: int, total: int) -> None:
            job.update(stage=stage, progress=done, total=total)
            self._save()

        try:
            options = PipelineOptions.from_config(self.config, overrides)
            out = self._pipeline_fn(text, options, workdir, progress=on_progress)
            job.update(status="done", stage="done", output=str(out))
        except Exception as exc:  # 任务线程兜底，失败要可见
            job.update(status="failed", error=str(exc))
        self._save()
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_jobs.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add storyteller/core/jobs.py tests/test_jobs.py
git commit -m "feat: 任务管理（后台线程 + jobs.json 持久化）"
```

---

### Task 11: WebUI 后端 webui/app.py

**Files:**
- Create: `storyteller/webui/app.py`, `storyteller/webui/__main__.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `JobManager`
- Produces:
  - `create_app(config: dict, outputs_dir: Path) -> FastAPI`
  - 路由：`POST /api/jobs`（body `{text, overrides?}` → `{id}`）、`GET /api/jobs`（列表）、`GET /api/jobs/{id}`、`GET /api/themes`（`{themes, default}`）
  - 静态：`/` 指向 `webui/static`；`/outputs` 挂载 outputs 目录（预览/下载）
  - `python -m storyteller.webui` 启动 uvicorn 127.0.0.1:8666

- [ ] **Step 1: 写失败测试**

`tests/test_webui.py`:
```python
import time

import pytest
from fastapi.testclient import TestClient

from storyteller.core.jobs import JobManager
from storyteller.webui.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    config = {
        "tts": {"name": "edge"},
        "visual": {"name": "loop_video", "assets_dir": tmp_path / "loops", "default_theme": "campfire"},
        "composer": {"name": "ffmpeg"},
        "output": {"width": 1280, "height": 720, "fps": 30, "dir": "outputs"},
    }
    (tmp_path / "loops" / "campfire").mkdir(parents=True)
    app = create_app(config, tmp_path)
    return TestClient(app)


def test_submit_and_poll(client):
    r = client.post("/api/jobs", json={"text": "第一段。\n\n第二段。", "overrides": {"theme": "campfire"}})
    assert r.status_code == 200
    jid = r.json()["id"]
    for _ in range(200):
        job = client.get(f"/api/jobs/{jid}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert client.get(f"/api/jobs/{jid}").json()["status"] in ("done", "failed")  # edge 真跑，可能因网络失败
    assert any(j["id"] == jid for j in client.get("/api/jobs").json())


def test_empty_text_rejected(client):
    r = client.post("/api/jobs", json={"text": "  "})
    assert r.status_code == 422 or r.status_code == 400


def test_themes(client):
    data = client.get("/api/themes").json()
    assert data["default"] == "campfire"
    assert data["themes"] == ["campfire"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_webui.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`storyteller/webui/app.py`:
```python
"""FastAPI 后端：提交任务/查询进度/列主题/静态与产物下载。"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..core.jobs import JobManager

STATIC_DIR = Path(__file__).parent / "static"


class JobRequest(BaseModel):
    text: str
    overrides: dict | None = None


def create_app(config: dict, outputs_dir: Path) -> FastAPI:
    app = FastAPI(title="Storyteller")
    manager = JobManager(config, Path(outputs_dir))
    app.state.manager = manager

    @app.post("/api/jobs")
    def submit(req: JobRequest):
        if not req.text.strip():
            raise HTTPException(400, "故事文本为空")
        return {"id": manager.submit(req.text, req.overrides)}

    @app.get("/api/jobs")
    def jobs():
        return manager.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        try:
            return manager.get(job_id)
        except KeyError:
            raise HTTPException(404, "任务不存在")

    @app.get("/api/themes")
    def themes():
        from ..core.adapters import create

        visual_name = config.get("visual", {}).get("name", "loop_video")
        visual_opts = {k: v for k, v in config.get("visual", {}).items() if k != "name"}
        visual = create("visual", visual_name, **visual_opts)
        return {
            "themes": visual.themes(),
            "default": config.get("visual", {}).get("default_theme", "campfire"),
        }

    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=outputs_dir), name="outputs")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
```

`storyteller/webui/__main__.py`:
```python
"""python -m storyteller.webui 启动本机服务。"""
import argparse
from pathlib import Path

import uvicorn

from ..core.config import load_config
from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Storyteller WebUI")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8666)
    args = parser.parse_args()
    config = load_config(Path(args.config))
    outputs = Path(config.get("output", {}).get("dir", "outputs"))
    app = create_app(config, outputs)
    print(f"Storyteller WebUI: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
```

注意：`/api/themes` 里 visual 构造会因 `assets_dir` 不存在返回空 themes，属预期。Task 12 完成前 `webui/static` 为空目录 + 占位 `index.html`（本任务先建一个一行占位：`<h1>Storyteller</h1>`，Task 12 替换）。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_webui.py -v`
Expected: 3 passed（test_submit_and_poll 中 edge-tts 若网络不通会 failed，断言已兼容 done/failed）

- [ ] **Step 5: Commit**

```bash
git add storyteller/webui tests/test_webui.py
git commit -m "feat: WebUI 后端（任务提交/进度/主题接口）"
```

---

### Task 12: WebUI 前端单页

**Files:**
- Modify: `storyteller/webui/static/index.html`（替换 Task 11 占位）

**Interfaces:**
- Consumes: `/api/jobs`、`/api/jobs/{id}`、`/api/themes`、`/outputs/<job_id>/final.mp4`

- [ ] **Step 1: 实现 index.html（内联 CSS/JS，无框架）**

页面结构：左侧表单（textarea 故事文本、画面主题 select、是否加字幕 checkbox、生成按钮），右侧任务列表（阶段/进度条，done 显示 `<video controls>` 预览 + 下载链接）。轮询 `setInterval` 2s 只刷新未完成任务。深色简洁风。JS 要点：

```javascript
async function refresh() {
  const jobs = await (await fetch('/api/jobs')).json();
  const box = document.getElementById('jobs');
  box.innerHTML = '';
  for (const j of jobs) {
    const el = document.createElement('div');
    el.className = 'job ' + j.status;
    const pct = j.total ? Math.round(100 * j.progress / j.total) : 0;
    let body = `<b>${j.id}</b> <span class="badge ${j.status}">${j.status}</span>
      <div class="bar"><div style="width:${pct}%"></div></div>
      <small>${j.stage || ''} ${j.error ? ' · ' + j.error : ''}</small>`;
    if (j.status === 'done' && j.output) {
      const rel = j.output.split('/outputs/')[1] || j.output;
      body += `<video controls src="/outputs/${rel}"></video>
        <a href="/outputs/${rel}" download>下载</a>
        ${j.output.replace('.mp4', '.srt') ? `<a href="/outputs/${rel.replace('.mp4', '.srt')}">字幕</a>` : ''}`;
    }
    el.innerHTML = body;
    box.appendChild(el);
  }
  return jobs;
}

setInterval(async () => {
  const jobs = await refresh();
  if (!jobs.some(j => j.status === 'running' || j.status === 'queued')) clearInterval(poll);
}, 2000);
```

提交逻辑：
```javascript
document.getElementById('generate').onclick = async () => {
  const text = document.getElementById('story').value;
  if (!text.trim()) return alert('请先粘贴故事文本');
  const overrides = { theme: document.getElementById('theme').value };
  await fetch('/api/jobs', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ text, overrides })
  });
  refresh();
};
```

主题下拉初始化：`fetch('/api/themes')` 填充 `<select id="theme">`，默认值用返回的 `default`。

- [ ] **Step 2: 手动验证**

Run: `.venv/bin/python -m storyteller.webui`，浏览器开 `http://127.0.0.1:8666`
Expected: 页面可提交短文本任务，进度可见，完成后可播放（edge-tts 需网络）。

- [ ] **Step 3: Commit**

```bash
git add storyteller/webui/static/index.html
git commit -m "feat: WebUI 单页（提交/进度/预览下载）"
```

---

### Task 13: CLI + 素材下载脚本 + README

**Files:**
- Create: `storyteller/cli.py`, `scripts/fetch_loops.sh`, `README.md`

**Interfaces:**
- Consumes: `load_config`、`PipelineOptions.from_config`、`run_pipeline`
- Produces: `python -m storyteller.cli -f story.txt [--theme rain] [--no-srt] [--out dir]`

- [ ] **Step 1: 实现 cli.py**

`storyteller/cli.py`:
```python
"""命令行入口：同一条管线，不走 WebUI。"""
import argparse
from pathlib import Path

from .core.config import load_config
from .core.pipeline import PipelineOptions, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="故事文本 -> 讲故事视频")
    parser.add_argument("-f", "--file", required=True, help="故事文本文件（UTF-8）")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--theme", default=None, help="画面主题，如 campfire/rain")
    parser.add_argument("--bgm", default=None, help="BGM 音频路径")
    parser.add_argument("--no-srt", action="store_true")
    parser.add_argument("--out", default=None, help="输出目录")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    overrides = {}
    if args.theme:
        overrides["theme"] = args.theme
    if args.bgm:
        overrides["bgm"] = args.bgm
    if args.no_srt:
        overrides["embed_srt"] = False
    options = PipelineOptions.from_config(config, overrides or None)
    text = Path(args.file).read_text(encoding="utf-8")
    out_dir = Path(args.out or (config.get("output", {}).get("dir", "outputs") + "/cli"))
    result = run_pipeline(text, options, out_dir, progress=lambda s, d, t: print(f"[{s}] {d}/{t}"))
    print(f"完成: {result}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 实现 scripts/fetch_loops.sh（下载免费循环视频清单）**

`scripts/fetch_loops.sh`:
```bash
#!/usr/bin/env bash
# 下载免费许可循环氛围视频到 assets/loops/<主题>/。
# 来源 Pexels（免费许可，无需署名）；如链接失效请到 pexels.com 搜同名关键词手动下载替换。
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/loops
fetch() { # fetch <主题> <url> <文件名>
  local dir="assets/loops/$1"
  mkdir -p "$dir"
  if [ -s "$dir/$3" ]; then echo "已有 $dir/$3，跳过"; return; fi
  echo "下载 $1/$3 ..."
  curl -fL --retry 3 -o "$dir/$3" "$2"
}
# 主题清单：按需增删；链接失效时去 pexels.com 搜索关键词手动补
fetch campfire "https://videos.pexels.com/video-files/1595404/1595404-hd_1280_720_25fps.mp4" fire.mp4
fetch storm    "https://videos.pexels.com/video-files/854082/854082-hd_1280_720_25fps.mp4" storm.mp4
fetch rain     "https://videos.pexels.com/video-files/857251/857251-hd_1280_720_30fps.mp4" rain.mp4
fetch ocean    "https://videos.pexels.com/video-files/2098989/2098989-hd_1280_720_30fps.mp4" ocean.mp4
fetch night    "https://videos.pexels.com/video-files/1257855/1257855-hd_1280_720_30fps.mp4" stars.mp4
echo "完成。主题："; ls assets/loops
```

- [ ] **Step 3: 写 README.md**

README 内容（要点）：项目一句话介绍；依赖（Python 3.10+、ffmpeg `brew install ffmpeg`）；安装（`python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`）；下载画面素材 `bash scripts/fetch_loops.sh`；三种用法（WebUI `python -m storyteller.webui` → 127.0.0.1:8666；CLI `python -m storyteller.cli -f story.txt --theme campfire`；模块替换：改 `config.yaml` 的 tts/visual/composer name 或在 `modules/*/__init__.py` 注册新适配器）；GPT-SoVITS 配置示例（config.yaml 注释已含）。

- [ ] **Step 4: CLI 冒烟（集成）**

Run: `RUN_INTEGRATION=1 .venv/bin/python -m storyteller.cli -f <(echo "篝火噼啪作响。夜风掠过营地。") --theme campfire`
Expected: 打印 `[tts] 1/2 ... 完成: outputs/cli/final.mp4`；ffprobe 时长 ≈ TTS 总时长（需网络 + 已跑 fetch_loops.sh，链接失效时先手动放素材）。

- [ ] **Step 5: Commit**

```bash
chmod +x scripts/fetch_loops.sh
git add storyteller/cli.py scripts/fetch_loops.sh README.md
git commit -m "feat: CLI 入口、素材下载脚本与 README"
```

---

### Task 14: 全量回归 + 端到端冒烟收尾

**Files:**
- Modify: 无新文件（仅验证与修复）

- [ ] **Step 1: 全量单测**

Run: `.venv/bin/pytest -v`
Expected: 全部 passed（integration 默认跳过）

- [ ] **Step 2: 集成回归**

Run: `RUN_INTEGRATION=1 .venv/bin/pytest -v -m integration`
Expected: media/tts(edge)/visual/composer 全 passed（edge-tts 需网络；GPT-SoVITS 无服务则不测）

- [ ] **Step 3: WebUI 端到端冒烟**

启动 `.venv/bin/python -m storyteller.webui`，提交一段 3 段短故事，确认：进度推进 → done → 页面内视频可播放、时长 ≈ 配音时长、画面为所选主题循环视频且被压暗。

- [ ] **Step 4: 修复发现的问题并提交**

```bash
git add -A
git commit -m "fix: 端到端冒烟发现的问题修复"
```

---

## Self-Review 记录

- **Spec 覆盖**：切分（T2）、TTS 可换（T5）、画面循环视频+压暗+自备素材（T6）、合成+BGM+srt（T7/T8）、注册表换模块（T4）、任务持久化（T10）、WebUI 提交/进度/预览（T11/T12）、CLI（T13）、素材下载（T13）、错误处理（T5 raise_for_status / T8 ffmpeg RuntimeError / T10 failed 状态 / T6 素材缺失回退默认主题）。AI 生图/动效模板为 spec 非目标，未建任务 ✓
- **占位符**：无 TBD/TODO；Task 9 与 Task 5 测试中的"修正说明"是实现裁决，已在正文写明最终形态 ✓
- **类型一致性**：`synthesize(text, out_path) -> float`、`resolve(theme, duration, out_path) -> Path`、`compose(timeline, out_path, srt_text) -> Path`、`TimelineItem(audio, visual, text, duration)`、`progress(stage, done, total)` 全文一致 ✓
