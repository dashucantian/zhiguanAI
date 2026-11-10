@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "PY=C:\Users\tiand\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
echo 正在起 Qoder 客户端窗口桥（127.0.0.1:8792）……
echo 这个窗口要开着，群里才能用它回答；关掉窗口，桥就停。
"%PY%" -m ai_router.qoder_bridge
echo.
pause
