import pytest

from storyteller.core import adapters


class Fake:
    def __init__(self, a=None):
        self.a = a


def test_register_and_create():
    # 名字用独立前缀，避免与其它测试注册的 "fake" 适配器冲突（注册表全局共享）
    adapters.register("tts", "probe_only", Fake)
    obj = adapters.create("tts", "probe_only", a=1)
    assert isinstance(obj, Fake) and obj.a == 1


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="未知模块类型"):
        adapters.create("nosuch", "x")


def test_unknown_name_raises():
    with pytest.raises(ValueError, match="未注册的适配器"):
        adapters.create("tts", "nope")
