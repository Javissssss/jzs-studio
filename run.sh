#!/usr/bin/env bash
# 巨人之上 · 内容工作台 — macOS / Linux launcher
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  巨人之上 · 内容工作台  jzs-studio"
echo "============================================"

PY=python3
command -v $PY >/dev/null 2>&1 || PY=python
command -v $PY >/dev/null 2>&1 || { echo "[错误] 未找到 Python 3.10+"; exit 1; }

echo "[1/4] Python: $($PY --version)"

echo "[2/4] 检查依赖..."
$PY -c "import flask, playwright" >/dev/null 2>&1 || {
  echo "       安装依赖中..."
  $PY -m pip install -r requirements.txt
}

echo "[3/4] 检查浏览器内核..."
$PY -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()" >/dev/null 2>&1 || {
  echo "       首次运行需下载浏览器内核(约120MB)..."
  $PY -m playwright install chromium
}

if [ -z "$PEXELS_API_KEY" ]; then
  echo "[提示] 未设置 PEXELS_API_KEY，氛围配图不可用（框架图/数据图不受影响）"
fi

echo "[4/4] 启动服务: http://127.0.0.1:8770"
echo "      Ctrl+C 停止"
( sleep 1; command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8770 || command -v open >/dev/null && open http://127.0.0.1:8770 ) &
$PY app.py --port 8770
