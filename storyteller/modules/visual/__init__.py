from ...core.adapters import register
from .loop_video import LoopVideo
from .still_slideshow import StillSlideshow

register("visual", "loop_video", LoopVideo)
register("visual", "still_slideshow", StillSlideshow)
