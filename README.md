# Storyteller

故事文本 → TTS 配音 + 循环氛围视频画面 → 讲故事视频（mp4）。画面只是氛围陪衬：内置免费许可循环视频（篝火、风暴、雨夜等），按配音时长循环播放并轻微压暗。各模块（TTS / 画面 / 合成）接口化，可独立替换。

## 依赖

- Python 3.10+
- ffmpeg / ffprobe（`brew install ffmpeg`）

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
bash scripts/fetch_loops.sh   # 下载画面素材（Pexels 免费许可）
```

## 用法

### WebUI（推荐）

```bash
.venv/bin/python -m storyteller.webui
# 打开 http://127.0.0.1:8666
```

左侧粘贴故事文本（空行分段，每段一次画面切换）、选主题、点生成；右侧看进度、预览与下载。

### 命令行

```bash
.venv/bin/python -m storyteller.cli -f story.txt --theme campfire
# 可选：--bgm music.mp3 --no-srt --out mydir
```

输出在 `outputs/<任务id>/final.mp4`（含同名 `.srt` 字幕，可在 config.yaml 打开内嵌）。

### 切换模块

编辑 `config.yaml`：

```yaml
tts:
  name: gpt_sovits        # 或 edge（零配置，联网即可用）
  base_url: http://127.0.0.1:9880
  ref_audio_path: /path/to/ref.wav
  prompt_text: 参考音频说的话

visual:
  name: loop_video        # 或 still_slideshow（图片轮播）
```

新增适配器：实现 `synthesize(text, out_path) -> float` / `resolve(theme, duration, out_path) -> Path` / `compose(timeline, out_path, srt_text) -> Path` 之一，放到 `storyteller/modules/<域>/` 并在对应 `__init__.py` 里 `register("<域>", "<名字>", 类)`。

## 自备素材

把 mp4（或 png/jpg）放进 `assets/loops/<主题>/` 即成为新主题；主题缺失素材时自动回退默认主题。

## 测试

```bash
.venv/bin/pytest                        # 单元测试
RUN_INTEGRATION=1 .venv/bin/pytest -m integration   # 含 ffmpeg/网络
```
