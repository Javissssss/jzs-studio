@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 一稿 · 内容工作台

echo ============================================
echo   一稿 · 内容工作台  jzs-studio
echo ============================================
echo.

REM --- locate python ---
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
  echo [错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH
  echo 下载: https://www.python.org/downloads/
  pause
  exit /b 1
)
echo [1/4] Python: 
%PY% --version

REM --- deps ---
echo [2/4] 检查依赖 (requirements.txt)...
%PY% -m pip install -q -r requirements.txt
if errorlevel 1 ( echo [错误] 依赖安装失败，检查网络或 pip 源 & pause & exit /b 1 )

REM --- playwright chromium ---
echo [3/4] 检查浏览器内核 (playwright chromium)...
%PY% -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()" >nul 2>nul
if errorlevel 1 (
  echo        首次运行需下载浏览器内核(约120MB)，请稍候...
  %PY% -m playwright install chromium
)

REM --- env hint ---
if not exist ".env" (
  echo [提示] 首次使用：打开页面右上角「设置」填写写作模型 / Pexels / 公众号等配置
  echo        配置保存在本目录 .env，换电脑时把 .env 一起拷过去即可
)

REM --- start ---
echo [4/4] 启动服务...
echo.
echo   打开浏览器访问:  http://127.0.0.1:8770
echo   关闭此窗口即停止服务
echo.
start "" http://127.0.0.1:8770
%PY% app.py --port 8770

endlocal
