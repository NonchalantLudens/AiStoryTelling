#!/usr/bin/env bash
# 权限自检：屏幕录制 + 辅助功能（制作演示视频的前置条件）
set -uo pipefail
export PATH="/opt/homebrew/bin:$PATH"

fail=0

echo "== 1/2 屏幕录制权限 =="
screencapture -x /tmp/_perm_shot.png 2>/dev/null
if [ -s /tmp/_perm_shot.png ]; then
  size=$(stat -f%z /tmp/_perm_shot.png)
  echo "OK: 截图成功（${size} 字节）。注意：若截图只有壁纸没有窗口，仍需到 系统设置 → 隐私与安全性 → 屏幕录制 授权本终端。"
else
  echo "FAIL: 截图失败 → 系统设置 → 隐私与安全性 → 屏幕录制"
  fail=1
fi

echo "== 2/2 辅助功能权限（System Events）=="
if osascript -e 'tell application "System Events" to get name of first application process' >/dev/null 2>&1; then
  echo "OK: System Events 可用"
else
  echo "FAIL: 未能访问 System Events → 系统设置 → 隐私与安全性 → 辅助功能，授权运行本脚本的终端 App"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "== 权限自检通过 =="
else
  echo "== 存在未授权项，请授权后重跑 =="
  exit 1
fi
