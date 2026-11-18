#!/bin/bash
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Python 3（python.org），然后重新双击本文件。"
  read -r -p "按回车键关闭…" _
  exit 1
fi
python3 app/server.py
read -r -p "程序已退出，按回车键关闭窗口…" _
