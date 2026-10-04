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
