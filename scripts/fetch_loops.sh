#!/usr/bin/env bash
# 下载免费许可循环氛围视频到 assets/loops/<主题>/。
# 来源 Pexels（免费许可，无需署名）；如链接失效请到 pexels.com 搜同名关键词手动下载替换。
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/loops
fetch() { # fetch <主题> <url> <文件名>
  local dir="assets/loops/$1"
  mkdir -p "$dir"
  if [ -s "$dir/$3" ]; then echo "已有 $dir/$3，跳过"; return; fi
  echo "下载 $1/$3 ..."
  curl -fL --retry 3 -o "$dir/$3" "$2"
}
# 主题清单：按需增删；链接失效时去 pexels.com 搜索关键词手动补
fetch campfire "https://videos.pexels.com/video-files/1595404/1595404-hd_1280_720_25fps.mp4" fire.mp4
fetch storm    "https://videos.pexels.com/video-files/854082/854082-hd_1280_720_25fps.mp4" storm.mp4
fetch rain     "https://videos.pexels.com/video-files/857251/857251-hd_1280_720_30fps.mp4" rain.mp4
fetch ocean    "https://videos.pexels.com/video-files/2098989/2098989-hd_1280_720_30fps.mp4" ocean.mp4
fetch night    "https://videos.pexels.com/video-files/1257855/1257855-hd_1280_720_30fps.mp4" stars.mp4
echo "完成。主题："
ls assets/loops
