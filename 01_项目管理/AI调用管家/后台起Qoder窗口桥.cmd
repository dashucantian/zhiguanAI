@echo off
rem Background launcher for the Qoder window bridge (port 8792).
rem No pause: this is what the scheduled task and the watchdog call.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "PY=C:\Users\tiand\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m ai_router.qoder_bridge
