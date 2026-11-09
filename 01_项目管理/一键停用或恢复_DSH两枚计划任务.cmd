@echo off
chcp 65001 >nul
title 止观AI｜DSH 两枚计划任务 停用与恢复
color 0F

echo ==========================================================
echo   止观AI｜DSH 两枚计划任务：停用 / 恢复
echo   本窗（协调位 AI-034·e12943a8）无权停用系统计划任务，
echo   本文件让您在管理员身份下双击即可完成。
echo ==========================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
  echo 需要管理员权限，正在为您提权，请在新弹出的窗口里按提示确认...
  echo.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

echo 当前状态：
echo.
schtasks /query /tn "DSH_Run_2h" /fo LIST /v | findstr /i "TaskName Status Next Run"
echo.
schtasks /query /tn "DSH_C3_Archive_1830" /fo LIST /v | findstr /i "TaskName Status Next Run"
echo.

set /p CH=请选择：1=停用这两枚（推荐）  2=恢复启用  直接回车=取消 =
if "%CH%"=="1" goto DISABLE
if "%CH%"=="2" goto ENABLE
echo 已取消，未改动任何东西。
pause
exit /b 0

:DISABLE
echo.
echo 正在停用 DSH_Run_2h（每 2 小时的连续执行器）...
schtasks /change /tn "DSH_Run_2h" /disable
echo 正在停用 DSH_C3_Archive_1830（10-21 已跑完的一次性归档任务）...
schtasks /change /tn "DSH_C3_Archive_1830" /disable
echo.
echo 结果复查：
schtasks /query /tn "DSH_Run_2h" /fo LIST /v | findstr /i "TaskName Status"
schtasks /query /tn "DSH_C3_Archive_1830" /fo LIST /v | findstr /i "TaskName Status"
goto END

:ENABLE
echo.
echo 正在恢复 DSH_Run_2h ...
schtasks /change /tn "DSH_Run_2h" /enable
echo 正在恢复 DSH_C3_Archive_1830 ...
schtasks /change /tn "DSH_C3_Archive_1830" /enable
echo.
echo 结果复查：
schtasks /query /tn "DSH_Run_2h" /fo LIST /v | findstr /i "TaskName Status"
schtasks /query /tn "DSH_C3_Archive_1830" /fo LIST /v | findstr /i "TaskName Status"
goto END

:END
echo.
echo 说明：两枚任务的原始 XML 已备份在
echo   D:\Project\zhiguanAI\_analysis_tmp\bak_20261109_gov\
echo 停用只是不再触发，不删除任务定义，随时可以用本文件选 2 恢复。
echo.
pause
