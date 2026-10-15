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
echo [2/4] 检查依赖 (flask, playwright)...
%PY% -c "import flask, playwright" >nul 2>nul
if errorlevel 1 (
  echo        安装依赖中...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 ( echo [错误] 依赖安装失败 & pause & exit /b 1 )
)

REM --- playwright chromium ---
echo [3/4] 检查浏览器内核 (playwright chromium)...
%PY% -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()" >nul 2>nul
if errorlevel 1 (
  echo        首次运行需下载浏览器内核(约120MB)，请稍候...
  %PY% -m playwright install chromium
)

REM --- env hint ---
if not defined PEXELS_API_KEY (
  echo [提示] 未设置 PEXELS_API_KEY，氛围配图将不可用（框架图/数据图不受影响）
  echo        设置方法: setx PEXELS_API_KEY "你的key"  然后重开终端
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
