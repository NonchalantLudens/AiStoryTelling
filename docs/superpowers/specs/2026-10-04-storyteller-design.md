# Storyteller 设计文档

日期：2026-10-04
状态：已与用户确认

## 目标

本地个人工具：输入故事文本，自动生成"配音 + 氛围循环画面"的讲故事视频。各模块（TTS、画面、合成）接口化，可独立替换。提供简单 WebUI。

## 非目标（第一版不做）

- AI 生图（留插件位）
- 多用户/部署到服务器
- 精细字幕对齐（提供基于段落时长的近似 srt，可选）

## 运行形态

本机运行，WebUI 仅本机访问（127.0.0.1）。依赖：Python 3.10+、ffmpeg（系统安装）、fastapi、uvicorn。

## 架构

```
storyteller/
  core/
    pipeline.py     # 编排：切分 → TTS → 画面 → 合成
    adapters.py     # 模块注册表：按配置名实例化适配器
    jobs.py         # 任务管理（后台线程 + 本地 json 持久化）
  modules/
    tts/
      base.py       # TTSEngine 接口：synthesize(text) -> (wav_path, duration)
      gpt_sovits.py # 调用 GPT-SoVITS API 服务
      edge.py       # edge-tts 零配置兜底（管线联调用）
    visual/
      base.py       # VisualSource 接口：resolve(segment, duration) -> 视频片段
      loop_video.py # 内置免费循环视频库（篝火/风暴/雨夜…）+ 用户自备素材
      still_slideshow.py  # 图片轮播（备用适配器）
    composer/
      base.py       # Composer 接口：compose(segments, bgm) -> mp4
      ffmpeg_composer.py
  webui/
    app.py          # FastAPI：提交任务/查询进度/列素材/下载结果
    static/         # 单页 UI（index.html + js，无框架）
  cli.py            # 命令行跑同一条管线
config.yaml         # 选模块、API 地址、输出参数（分辨率/帧率/BGM 音量）
```

## 数据流

1. **切分**：故事文本按段落（空行）切分，长段落再按句子二次切分；每段 = 一次画面切换的最小单位。
2. **TTS**：每段调用所选 TTS 适配器 → 单段音频文件 + 时长。
3. **画面**：每段按配置的画面主题（如"篝火"）取对应循环视频，截取/循环到该段时长；轻微压暗（亮度 0.85 左右）避免喧宾夺主。
4. **合成**：ffmpeg 按段 concat 音画，可选 BGM（音量自动压低、循环），输出 `outputs/<job>/final.mp4`，可选近似 srt。

## 模块接口（可换性）

- `TTSEngine.synthesize(text: str, out_path: Path) -> float`（返回时长秒）
- `VisualSource.resolve(theme: str, duration: float, out_path: Path) -> Path`
- `Composer.compose(timeline: list[TimelineItem], out_path: Path) -> Path`
- 适配器通过 `config.yaml` 中名字选择；注册表在 `core/adapters.py`。

## 内置画面素材

- 免费许可循环视频（Pexels/Coverr 等），存放 `assets/loops/<theme>/`，每主题 1-3 个。
- 第一批主题：篝火、风暴中的屋子、雨夜窗前、海浪、夜空。视频不入 git，提供 `scripts/fetch_loops.sh` 下载清单 + 手动放置说明。
- WebUI 可查看已有主题/上传自备视频。

## WebUI

单页：
- 左：粘贴/编辑故事文本，选 TTS 与画面主题、BGM、分辨率。
- 提交 → 任务卡（进度条、阶段状态）→ 完成后内嵌预览 + 下载。
- 任务列表持久化在 `outputs/jobs.json`，重启不丢。

## 错误处理

- TTS 适配器失败：单段重试 2 次；仍失败则任务标记 failed 并保留日志。
- ffmpeg 失败：保留中间文件供调试（`outputs/<job>/`）。
- 素材缺失：提示主题未下载，回退到默认主题。

## 测试

- 单测：切分逻辑、适配器注册表、timeline 生成（mock TTS/合成）。
- 集成冒烟：edge-tts（无 Key）+ 合成一条 3 段短视频，验证 mp4 时长 ≈ 音频总时长。
