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
    result = run_pipeline(
        text, options, out_dir,
        progress=lambda s, d, t: print(f"[{s}] {d}/{t}"),
    )
    print(f"完成: {result}")


if __name__ == "__main__":
    main()
