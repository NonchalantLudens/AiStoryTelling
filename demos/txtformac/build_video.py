#!/usr/bin/env python3
"""合成 TXTForMac 演示视频。

用法:
  python3 build_video.py narration     # 只生成分段解说 mp3
  python3 build_video.py build         # 全流程：对齐/拼接/双语字幕烧录 → outputs/final.mp4

流程:
  1. 每段解说 edge-tts（云野）→ narration/<id>.mp3，探测时长
  2. 视频段时长 vs 解说时长：视频短则定格补齐（tpad=clone），长则截断
  3. 全屏录屏按窗口矩形裁剪 → 统一 1920x1080 30fps → concat
  4. 解说音轨按段起点对齐混入 → 双语 srt 烧录
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# 优先用 ffmpeg-full（带 libass 字幕滤镜）
_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin")
if (_FULL / "ffmpeg").exists():
    os.environ.setdefault("FFMPEG_BIN", str(_FULL / "ffmpeg"))
    os.environ.setdefault("FFPROBE_BIN", str(_FULL / "ffprobe"))

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))  # 引入 storyteller 包

from storyteller.core.media import probe_duration, run_ffmpeg  # noqa: E402

import edge_tts  # noqa: E402

SB = yaml.safe_load((HERE / "storyboard.yaml").read_text(encoding="utf-8"))
SEG_DIR = HERE / "outputs" / "segments"
NAR_DIR = HERE / "outputs" / "narration"
FINAL = HERE / "outputs" / "final.mp4"
SRT = HERE / "outputs" / "final.srt"
VOICE = "zh-CN-YunjianNeural"  # 云健·浑厚解说（edge 免费列表中最接近纪录片风格；云野是 Azure 付费音色）
RATE = "-4%"          # 解说稍慢一点点，更沉稳
PAD = 0.7             # 每段视频比解说多出的定格余量（秒）
OUT_W, OUT_H, FPS = 1920, 1080, 30


def synth(text: str, path: Path, attempts: int = 4):
    async def _run():
        comm = edge_tts.Communicate(text, VOICE, rate=RATE)
        await comm.save(str(path))

    for i in range(attempts):
        try:
            asyncio.run(_run())
            if path.exists() and path.stat().st_size > 0:
                return
        except Exception as exc:
            if i == attempts - 1:
                raise
            print(f"    [retry] edge-tts 第 {i + 1} 次失败: {exc}")
            time.sleep(1.5 * (i + 1))


def narration_only():
    NAR_DIR.mkdir(parents=True, exist_ok=True)
    durations = {}
    for seg in SB["segments"]:
        out = NAR_DIR / f"{seg['id']}.mp3"
        ok = False
        if out.exists():
            try:
                durations[seg["id"]] = probe_duration(out)
                ok = True
            except RuntimeError:
                out.unlink()
        if not ok:
            print(f"[tts] {seg['id']} 生成中…")
            synth(seg["narration"]["zh"], out)
            durations[seg["id"]] = probe_duration(out)
    (NAR_DIR / "durations.json").write_text(
        json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("解说时长:", json.dumps(durations, ensure_ascii=False))


def _display_scale(video_w: int) -> float:
    """录屏像素宽 / 屏幕逻辑点宽 = Retina 缩放系数。"""
    try:
        import Quartz

        b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        pts_w = b.size.width
        if pts_w and pts_w > 100:
            s = video_w / pts_w
            if 1.0 <= s <= 4.0:
                return s
    except Exception:
        pass
    return 2.0  # Retina 默认


def _crop_expr(video_w: int, video_h: int, rect: dict) -> str:
    """按窗口矩形裁剪并取 16:9，返回 ffmpeg crop 参数串。"""
    scale = _display_scale(video_w)
    x = max(0, int(rect["x"] * scale))
    y = max(0, int(rect["y"] * scale))
    w = min(max(int(rect["w"] * scale), 16), video_w - x)
    h = min(max(int(rect["h"] * scale), 16), video_h - y)
    if w < 16 or h < 16:
        return f"scale={OUT_W}:{OUT_H},setsar=1"
    # 调整到 16:9（高度按宽度算，顶部对齐——标题栏重要）
    target_h = int(w * 9 / 16)
    if target_h <= video_h - y:
        h = min(h, target_h) if target_h <= h else h
        if h < target_h:
            w = int(h * 16 / 9)
            target_h = h
        else:
            h = target_h
    else:
        h = video_h - y
        w = min(w, int(h * 16 / 9))
    x = min(x, max(0, video_w - w))
    return f"crop={w}:{h}:{x}:{y},scale={OUT_W}:{OUT_H},setsar=1"


def _fmt_ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build(skip_missing: bool = False):
    NAR_DIR.mkdir(parents=True, exist_ok=True)
    narration_only()  # 幂等
    durations = json.loads((NAR_DIR / "durations.json").read_text(encoding="utf-8"))

    work = HERE / "outputs" / "build"
    work.mkdir(parents=True, exist_ok=True)
    norm_files: list[Path] = []
    srt_blocks: list[str] = []
    timeline = 0.0

    for seg in SB["segments"]:
        sid = seg["id"]
        mov = SEG_DIR / f"{sid}.mov"
        if not mov.exists():
            if skip_missing:
                print(f"[skip] {sid} 未录制，跳过")
                continue
            print(f"缺少 {mov}，请先录制")
            sys.exit(1)
        video_dur = probe_duration(mov)
        nar_dur = durations[sid]
        target = max(video_dur, nar_dur + PAD)
        print(f"[{sid}] 视频 {video_dur:.2f}s 解说 {nar_dur:.2f}s → 目标 {target:.2f}s")

        # 窗口裁剪 + 定格补齐/截断 + 统一规格
        rect_file = mov.with_suffix(".rect.json")
        try:
            rect = json.loads(rect_file.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            import yaml as _yaml
            try:
                rect = _yaml.safe_load(rect_file.read_text()) or {"full": True}
            except Exception:
                rect = {"full": True}
        vf = "scale=%d:%d,setsar=1" % (OUT_W, OUT_H)
        if not rect.get("full"):
            try:
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height", "-of", "csv=p=0",
                     str(mov)],
                    capture_output=True, text=True,
                )
                vw, vh = (int(x) for x in probe.stdout.strip().split(","))
                vf = _crop_expr(vw, vh, rect)
            except ValueError:
                pass
        tpad = ",tpad=stop_mode=clone:stop_duration=%.3f" % max(0.0, target - video_dur) \
            if target > video_dur else ""
        norm = work / f"{sid}.mp4"
        run_ffmpeg([
            "-i", str(mov),
            "-vf", vf + tpad,
            "-t", f"{target:.3f}",
            "-r", str(FPS), "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-y", str(norm),
        ])
        norm_files.append(norm)

        # 双语字幕：本段时间轴
        start = timeline
        end = timeline + min(nar_dur + 0.5, target)
        zh = seg["narration"]["zh"]
        en = seg["narration"]["en"]
        idx = len(srt_blocks) // 1 + 1
        srt_blocks.append(f"{idx}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{zh}\n{en}")
        timeline += target

    # 拼接
    concat_list = work / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{f.resolve()}'" for f in norm_files), encoding="utf-8"
    )
    merged = work / "merged.mp4"
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", "-y", str(merged),
    ])

    # 解说音轨按段起点混入
    inputs = ["-i", str(merged)]
    filter_parts = []
    amix_inputs = []
    t = 0.0
    n = 0
    for seg in SB["segments"]:
        sid = seg["id"]
        if not (SEG_DIR / f"{sid}.mov").exists():
            continue
        video_dur = probe_duration(SEG_DIR / f"{sid}.mov")
        target = max(video_dur, durations[sid] + PAD)
        nar = NAR_DIR / f"{sid}.mp3"
        inputs += ["-i", str(nar)]
        filter_parts.append(f"[{n + 1}:a]adelay={int(t * 1000)}|{int(t * 1000)}[a{n}]")
        amix_inputs.append(f"[a{n}]")
        t += target
        n += 1
    fc = ";".join(filter_parts) + f";{''.join(amix_inputs)}amix=inputs={n}:normalize=0[aout]"
    with_narr = work / "with_narr.mp4"
    run_ffmpeg([
        *inputs,
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-y", str(with_narr),
    ])

    # 双语字幕烧录
    SRT.write_text("\n\n".join(srt_blocks), encoding="utf-8")
    run_ffmpeg([
        "-i", str(with_narr),
        "-vf", f"subtitles=filename={SRT}:force_style="
               "'FontSize=15,Outline=2,MarginV=40'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        "-y", str(FINAL),
    ])
    print(f"成片: {FINAL}（{probe_duration(FINAL):.1f}s）")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    if mode == "narration":
        narration_only()
    elif mode == "build":
        build(skip_missing=True)
    else:
        print("用法: build_video.py narration|build")
        sys.exit(1)
