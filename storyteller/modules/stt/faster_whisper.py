"""faster-whisper 适配器：本地 STT，支持音视频（PyAV 解码），模型进程内缓存。

首次运行会下载模型；国内网络默认走 hf-mirror 镜像并禁用 xet 通道
（可用环境变量 HF_ENDPOINT / HF_HUB_DISABLE_XET 覆盖）。
"""
import os
from pathlib import Path


class FasterWhisper:
    name = "faster_whisper"
    _models: dict = {}  # (model_size, device, compute_type) -> WhisperModel

    def __init__(
        self,
        model_size: str = "base",
        language: str = "zh",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type

    def _model(self):
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from faster_whisper import WhisperModel

        key = (self.model_size, self.device, self.compute_type)
        if key not in FasterWhisper._models:
            FasterWhisper._models[key] = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return FasterWhisper._models[key]

    def transcribe(self, media_path: Path) -> str:
        segments, _info = self._model().transcribe(
            str(media_path), language=self.language
        )
        return "".join(seg.text for seg in segments).strip()
