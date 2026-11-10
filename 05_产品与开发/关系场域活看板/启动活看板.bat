@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  start "" /min python build_field_model.py --watch --interval 2
) else (
  start "" /min py -3 build_field_model.py --watch --interval 2
)
start "" "index.html"