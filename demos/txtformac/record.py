#!/usr/bin/env python3
"""TXTForMac 演示录制引擎。

用法:
  python3 record.py smoke              # 5s 冒烟：录屏+裁剪验证
  python3 record.py segment <id>       # 重录指定段（见 storyboard.yaml）
  python3 record.py all                # 顺序录制全部段

原理:
  screencapture -v 全屏录制（SIGINT 停止）→ 按段保存 mov
  UI 操作由 ActionExecutor 执行（osascript System Events）
  窗口裁剪在 build_video.py 阶段做（build 时用 ffprobe/AppleScript 取窗口矩形）
"""
import subprocess
import sys
import time
from pathlib import Path

import Quartz
import json
import yaml

HERE = Path(__file__).parent
OUT = HERE / "outputs" / "segments"
SB = yaml.safe_load((HERE / "storyboard.yaml").read_text(encoding="utf-8"))
APP = SB["app"]
OWNER = SB["window_owner"]
DEMO_ROOT = Path(SB["demo_root"]).expanduser()

osascript = lambda *args: subprocess.run(
    ["osascript", "-e", *args], capture_output=True, text=True
)

# 特殊键 keycode；可打印字符走 Unicode 字符事件
KEYCODES = {
    "return": 36, "enter": 36, "escape": 53, "esc": 53, "tab": 48,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "w": 13, "f": 3, "o": 31, "s": 1, "n": 45, "z": 6, "x": 7,
    ",": 43, "]": 30, "[": 33,
}


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sh_ax_row_rect():
    """Finder 前窗文件列表第一行的屏幕矩形 (x, y, w, h)。"""
    sc = (
        'tell application "System Events" to tell process "Finder" '
        "to get {position, size} of row 1 of outline 1 of scroll area 1 of "
        "splitter group 1 of splitter group 1 of window 1"
    )
    r = osascript(sc)
    if r.returncode != 0:
        return None
    try:
        nums = [int(x.strip()) for x in r.stdout.strip().split(",")]
        return nums[0], nums[1], nums[2], nums[3]
    except (ValueError, IndexError):
        return None


def _cg_mouse(evtype, mx, my, btn=Quartz.kCGMouseButtonLeft):
    e = Quartz.CGEventCreateMouseEvent(None, evtype, (mx, my), btn)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)



def window_rect() -> tuple[int, int, int, int] | None:
    """返回 TXTForMac 前窗 (x, y, w, h)，Retina 下坐标已含缩放。"""
    sc = (
        'tell application "System Events" to tell process "%s" '
        "to get {position, size} of front window" % OWNER
    )
    r = osascript(sc)
    if r.returncode != 0:
        return None
    try:
        nums = [int(x.strip()) for x in r.stdout.strip().split(",")]
        return nums[0], nums[1], nums[2], nums[3]
    except (ValueError, IndexError):
        return None


class ActionExecutor:
    """执行分镜动作：键盘/菜单/文件打开/Finder 交互/鼠标事件。"""

    def __init__(self):
        self.app_launched = False
        self._rightclick_point = None

    def _activate_owner(self):
        osascript(f'tell application "{OWNER}" to activate')

    def _dismiss_tcc(self, tries: int = 6):
        """自动点击系统文件访问授权对话框的「允许」（对话框归 CoreServicesUIAgent）。"""
        for _ in range(tries):
            # 快路径：没有授权弹窗就直接返回
            chk = osascript(
                'tell application "System Events" to tell process '
                '"CoreServicesUIAgent" to count windows'
            )
            if chk.returncode == 0 and chk.stdout.strip() == "0":
                return
            clicked = False
            for sc in (
                f'tell application "System Events" to tell process "{OWNER}" '
                'to click button "允许" of window 1',
                'tell application "System Events" to tell process "CoreServicesUIAgent" '
                "to click button 1 of window 1",
                f'tell application "System Events" to tell process "{OWNER}" '
                'to click button "OK" of window 1',
            ):
                r = osascript(sc)
                if r.returncode == 0:
                    clicked = True
                    print("    [tcc] 已点击允许")
                    break
            if not clicked:
                time.sleep(0.4)

    def exec(self, a: dict):
        do = a["do"]
        if do == "quit_app":
            osascript(f'tell application "{OWNER}" to quit')
            self.app_launched = False
            time.sleep(1.2)
        elif do == "launch":
            run(["open", APP])
            time.sleep(1.2)
            self._activate_owner()
            time.sleep(0.5)
            self.app_launched = True
        elif do == "activate":
            self._activate_owner()
        elif do == "wait":
            time.sleep(float(a.get("seconds", 1.0)))
        elif do == "key":
            combo = a["combo"]
            parts = combo.split("+")
            keyc = parts[-1]
            mods = parts[:-1]
            flag = 0
            keymap = {"cmd": Quartz.kCGEventFlagMaskCommand,
                      "shift": Quartz.kCGEventFlagMaskShift,
                      "alt": Quartz.kCGEventFlagMaskAlternate,
                      "ctrl": Quartz.kCGEventFlagMaskControl}
            for m in mods:
                flag |= keymap[m]
            code = KEYCODES.get(keyc.lower())
            if code is None:
                # 可打印字符：按字符事件并附修饰键
                e = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                Quartz.CGEventKeyboardSetUnicodeString(e, len(keyc), keyc)
                if flag:
                    Quartz.CGEventSetFlags(e, flag)
                Quartz.CGEventPost(0, e)
                e = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
                Quartz.CGEventKeyboardSetUnicodeString(e, len(keyc), keyc)
                if flag:
                    Quartz.CGEventSetFlags(e, flag)
                Quartz.CGEventPost(0, e)
            else:
                down = Quartz.CGEventCreateKeyboardEvent(None, code, True)
                up = Quartz.CGEventCreateKeyboardEvent(None, code, False)
                if flag:
                    Quartz.CGEventSetFlags(down, flag)
                    Quartz.CGEventSetFlags(up, flag)
                Quartz.CGEventPost(0, down)
                Quartz.CGEventPost(0, up)
            time.sleep(0.25)
        elif do == "type":
            text = a["text"]
            for ch in text:
                e = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                Quartz.CGEventKeyboardSetUnicodeString(e, len(ch), ch)
                Quartz.CGEventPost(0, e)
                e = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
                Quartz.CGEventKeyboardSetUnicodeString(e, len(ch), ch)
                Quartz.CGEventPost(0, e)
                time.sleep(0.06)
            time.sleep(0.2)
        elif do == "open_files":
            files = [str(DEMO_ROOT / f) for f in a["files"]]
            run(["open", "-a", APP, *files])
            time.sleep(1.0)
            self._activate_owner()
            self._dismiss_tcc()
        elif do == "menu":
            app = a["app"]
            path = a["path"]
            chain = "menu bar 1"
            items = " > ".join(path)
            try:
                sc = (f'tell application "System Events" to tell process "{app}" '
                      f'to click menu item "{path[-1]}" of menu 1 of '
                      f'menu item "{path[-2]}" of menu 1 of menu bar item 1 of menu bar 1')
                r = osascript(sc)
            except Exception:
                r = None
            if not r or r.returncode != 0:
                print(f"    [warn] 菜单 {items} 点击失败，回退快捷键")
                fallback = a.get("fallback")
                if fallback:
                    self.exec({"do": "key", "combo": fallback})
            time.sleep(0.6)
        elif do == "finder_reveal":
            target = str(DEMO_ROOT / a["rel"])
            run(["open", target])
            time.sleep(0.8)
            osascript('tell application "Finder" to activate')
            time.sleep(0.5)
            # 切到列表视图：行元素才有稳定的 AXShowMenu
            osascript(
                'tell application "Finder" to set current view of '
                "front Finder window to list view"
            )
            time.sleep(0.5)
        elif do == "finder_select":
            name = a["filename"]
            kind = a.get("kind", "file")   # file | folder | item
            sc = (
                f'tell application "Finder" to select the {kind} named '
                f'"{name}" of front Finder window'
            )
            r = osascript(sc)
            if r.returncode != 0:
                sc2 = (
                    'tell application "System Events" to tell process "Finder" '
                    "to select row 1 of outline 1 of scroll area 1 of "
                    "splitter group 1 of splitter group 1 of window 1"
                )
                r = osascript(sc2)
                if r.returncode != 0:
                    print(f"    [warn] Finder 选中失败: {r.stderr.strip()[:60]}")
            time.sleep(0.4)
        elif do == "scroll":
            for _ in range(int(a.get("times", 3))):
                osascript('tell application "System Events" to key code 121')  # page down
                time.sleep(0.35)
        elif do == "py_rightclick_row":
            """Quartz 真实右键 Finder 文件列表第一行（菜单保持打开）。"""
            r = sh_ax_row_rect()
            if r is None:
                print("    [warn] 取不到行矩形")
                return
            cx, cy = r[0] + r[2] // 2, r[1] + r[3] // 2
            _cg_mouse(Quartz.kCGEventMouseMoved, cx, cy)
            time.sleep(0.2)
            _cg_mouse(Quartz.kCGEventRightMouseDown, cx, cy, Quartz.kCGMouseButtonRight)
            _cg_mouse(Quartz.kCGEventRightMouseUp, cx, cy, Quartz.kCGMouseButtonRight)
            self._rightclick_point = (cx, cy)
            time.sleep(float(a.get("hold", 1.0)))
        elif do == "py_service_navigate":
            """右键菜单键盘导航：↑选中「服务」→ → 展开子菜单 → ↓ 到最后一项 TXTForMac 高亮。"""
            for code, gap in ((126, 0.3), (124, 0.6)):
                e = Quartz.CGEventCreateKeyboardEvent(None, code, True)
                Quartz.CGEventPost(0, e)
                e = Quartz.CGEventCreateKeyboardEvent(None, code, False)
                Quartz.CGEventPost(0, e)
                time.sleep(gap)
            for _ in range(12):
                e = Quartz.CGEventCreateKeyboardEvent(None, 125, True)
                Quartz.CGEventPost(0, e)
                e = Quartz.CGEventCreateKeyboardEvent(None, 125, False)
                Quartz.CGEventPost(0, e)
                time.sleep(0.12)
        elif do == "click_app_button":
            """点击 TXTForMac 前窗里的指定按钮（服务触发的「新建文档」对话框）。"""
            name = a["name"]
            sc = (
                f'tell application "System Events" to tell process "{OWNER}" '
                f'to click button "{name}" of window 1'
            )
            r = osascript(sc)
            if r.returncode != 0:
                print(f"    [warn] 按钮 {name} 点击失败: {r.stderr.strip()[:60]}")
            time.sleep(0.8)
        elif do == "py_click_offset":
            """相对右键点偏移处左键（点上下文菜单项）。"""
            dx, dy = int(a["dx"]), int(a["dy"])
            base = self._rightclick_point or (0, 0)
            mx, my = base[0] + dx, base[1] + dy
            _cg_mouse(Quartz.kCGEventMouseMoved, mx, my)
            time.sleep(0.25)
            _cg_mouse(Quartz.kCGEventLeftMouseDown, mx, my)
            _cg_mouse(Quartz.kCGEventLeftMouseUp, mx, my)
            time.sleep(0.8)
        else:
            raise ValueError(f"未知动作: {do}")


def record_segment(seg_id: str, actions: list[dict], out_path: Path, rect_owner: str):
    ex = ActionExecutor()
    print(f"[{seg_id}] 录制开始 → {out_path.name}")
    proc = subprocess.Popen(
        ["screencapture", "-v", "-x", str(out_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.8)  # 等录制起稳
    try:
        for a in actions:
            print(f"    {a['do']} {a.get('combo') or a.get('text') or a.get('files') or a.get('name') or a.get('rel') or ''}")
            ex.exec(a)
    finally:
        time.sleep(0.6)  # 收尾帧
        # 记录窗口矩形（激活目标 app 后多次重试，避开启动动画中的小窗）
        osascript(f'tell application "{rect_owner}" to activate')
        rect = None
        for _ in range(4):
            time.sleep(0.5)
            sc = (
                'tell application "System Events" to tell process "%s" '
                "to get {position, size} of front window" % rect_owner
            )
            r = osascript(sc)
            if r.returncode == 0:
                try:
                    nums = [int(x.strip()) for x in r.stdout.strip().split(",")]
                    cand = {"x": nums[0], "y": nums[1], "w": nums[2], "h": nums[3]}
                    if cand["w"] * cand["h"] > 400 * 300:
                        rect = cand
                        break
                    rect = cand  # 先记着，若有更大的再覆盖
                except (ValueError, IndexError):
                    pass
        rect_path = out_path.with_suffix(".rect.json")
        rect_path.write_text(json.dumps(rect or {"full": True}))
        proc.send_signal(subprocess.signal.SIGINT)
        proc.wait(timeout=10)
    print(f"[{seg_id}] 录制完成 rect={rect}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "smoke":
        out = OUT / "smoke.mov"
        print("冒烟：录制 5s 全屏（期间请勿操作）")
        proc = subprocess.Popen(
            ["screencapture", "-v", "-x", str(out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(5)
        proc.send_signal(subprocess.signal.SIGINT)
        proc.wait(timeout=10)
        rect = window_rect()
        print(f"窗口矩形: {rect}")
        print(f"产物: {out} ({out.stat().st_size if out.exists() else 0} 字节)")
        return

    segs = SB["segments"]
    targets = [s for s in segs if s["id"] == mode] if mode != "all" else segs
    if mode != "all" and not targets:
        print(f"未知段: {mode}，可选: {[s['id'] for s in segs]}")
        sys.exit(1)
    for seg in targets:
        out = OUT / f"{seg['id']}.mov"
        if out.exists():
            out.unlink()
        record_segment(seg["id"], seg["actions"], out, seg.get("rect_owner", OWNER))
        time.sleep(1.0)


if __name__ == "__main__":
    main()
