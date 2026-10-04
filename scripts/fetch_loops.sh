#!/usr/bin/env bash
# 下载免费许可循环氛围视频到 assets/loops/<主题>/。
# 来源 Pexels（免费许可，无需署名）；链接失效时到 pexels.com 搜同类关键词手动补。
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/loops
fetch() { # fetch <主题> <文件名> <url>
  local dir="assets/loops/$1"
  mkdir -p "$dir"
  if [ -s "$dir/$2" ]; then echo "已有 $dir/$2，跳过"; return; fi
  echo "下载 $1/$2 ..."
  curl -fL --retry 3 -o "$dir/$2" "$3"
}
# 以下直链均已验证可下载（2026-10-04）
fetch night     stars.mp4     "https://videos.pexels.com/video-files/857195/857195-hd_1280_720_25fps.mp4"
fetch night     earth.mp4     "https://videos.pexels.com/video-files/1851190/1851190-hd_1280_720_25fps.mp4"
fetch sunset    field.mp4     "https://videos.pexels.com/video-files/856973/856973-hd_1280_720_25fps.mp4"
fetch storm     lightning.mp4 "https://videos.pexels.com/video-files/854082/854082-hd_1280_720_25fps.mp4"
fetch ocean     waves.mp4     "https://videos.pexels.com/video-files/2098989/2098989-hd_1280_720_30fps.mp4"
fetch waterfall pool.mp4      "https://videos.pexels.com/video-files/2098988/2098988-hd_1280_720_30fps.mp4"
echo "完成。主题："
ls assets/loops
