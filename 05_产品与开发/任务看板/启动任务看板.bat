@echo off
chcp 65001 >nul
setlocal
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
cd /d "%~dp0"
echo.
echo   止观AI 可视化任务看板
echo   --------------------------------------
echo   浏览器会自动打开 http://127.0.0.1:8848
echo   关掉这个黑窗口 = 关掉看板
echo   只听本机回环，不对局域网开放
echo.
if not defined QIANWEN_API_KEY echo   [提示] 未检测到 QIANWEN_API_KEY，对话功能不可用；
if not defined QIANWEN_API_KEY echo          先双击项目根目录的 配置千问密钥.bat 设一次即可。
start "" http://127.0.0.1:8848
"%PY%" board_server.py
pause
