"""模块注册表：kind -> name -> 类。config.yaml 里选名字，这里实例化。"""
from typing import Any

_REGISTRY: dict[str, dict[str, type]] = {
    "tts": {},
    "visual": {},
    "composer": {},
}


def register(kind: str, name: str, cls: type) -> None:
    _REGISTRY.setdefault(kind, {})[name] = cls


def available(kind: str) -> list[str]:
    return sorted(_REGISTRY.get(kind, {}))


def create(kind: str, name: str, **opts: Any) -> Any:
    if kind not in _REGISTRY:
        raise ValueError(f"未知模块类型: {kind}")
    table = _REGISTRY[kind]
    if name not in table:
        raise ValueError(f"未注册的适配器: {kind}/{name}，可选: {sorted(table)}")
    return table[name](**opts)
