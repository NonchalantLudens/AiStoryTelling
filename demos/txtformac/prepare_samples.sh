#!/usr/bin/env bash
# 生成演示用样例文件：多标签文本、正则演示文本、GBK 编码文件、Finder 演示目录
set -euo pipefail
export PATH="/opt/homebrew/bin:$PATH"

DEMO_ROOT="$HOME/Desktop/TXTForMacDemo"
mkdir -p "$DEMO_ROOT/tabs" "$DEMO_ROOT/finder"

# 1) 多标签演示：三个标签文件
cat > "$DEMO_ROOT/tabs/第一章-启程.txt" <<'EOF'
第一章 启程

夜色像一块浸了水的绒布，覆盖在山谷之上。
少年背起行囊，火把的光在岩壁上摇晃。
他回头望了一眼村庄，然后迈出了第一步。
EOF

cat > "$DEMO_ROOT/tabs/第二章-溪谷.txt" <<'EOF'
第二章 溪谷

溪水在黑暗里低声歌唱。
第 1 块石头，第 2 块石头，第 3 块石头。
他数着石头过河，像数着自己的心跳。
EOF

cat > "$DEMO_ROOT/tabs/第三章-星空.txt" <<'EOF'
第三章 星空

银河从山脊后面升起来。
风停了，星星亮得惊人。
他想：故事才刚刚开始。
EOF

# 2) 查找替换正则演示：带编号的清单（用 \d+ 正则演示）
cat > "$DEMO_ROOT/regex-demo.txt" <<'EOF'
任务清单
第 1 天：抵达溪谷营地。
第 2 天：翻越北岭隘口。
第 3 天：穿过迷雾森林。
第 4 天：抵达星空湖。
装备编号 1001 号：火把。
装备编号 1002 号：绳索。
装备编号 1003 号：地图。
EOF

# 3) GBK 编码文件（编码识别演示）
iconv -f UTF-8 -t GBK <<'EOF' > "$DEMO_ROOT/gbk-legacy.txt"
这是一份来自旧系统的文档。
它使用 GBK 编码保存。
TXTForMac 可以正确识别并显示这些文字，避免乱码。
EOF

# 4) Finder 右键新建演示目录
cat > "$DEMO_ROOT/finder/已有笔记.txt" <<'EOF'
这是 Finder 演示目录里已有的笔记。
右键空白处或文件，可以看到 TXTForMac 的「新建文本文件」菜单项。
EOF

echo "样例文件就绪："
find "$DEMO_ROOT" -type f | sort
