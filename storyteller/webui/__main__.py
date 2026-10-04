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
