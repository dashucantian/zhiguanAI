@echo off
setlocal EnableExtensions EnableDelayedExpansion
title 止观AI｜DSH 两枚计划任务 停用与恢复
color 0F

echo ==========================================================
echo   止观AI｜DSH 两枚计划任务：停用 / 恢复
echo   管的是：DSH_Run_2h            每 2 小时跑一次连续执行器
echo           DSH_C3_Archive_1830   10-21 已跑完的一次性任务
echo ==========================================================
echo.

net session >nul 2>&1
if errorlevel 1 goto NEEDADMIN

:ADMIN
echo 当前状态：
call :SHOW
echo.
set "CH="
set /p "CH=请选择：1=停用这两枚（推荐）  2=恢复启用  直接回车=取消 = "
if "%CH%"=="1" goto DISABLE
if "%CH%"=="2" goto ENABLE
echo 已取消，未改动任何东西。
goto END

:NEEDADMIN
echo 需要管理员权限，正在提权，请在弹出的窗口点「是」...
echo （如果没有弹窗，说明被系统拦了，请右键本文件选「以管理员身份运行」）
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b 0

:DISABLE
echo.
echo 停用 DSH_Run_2h ...
schtasks /change /tn "DSH_Run_2h" /disable
if errorlevel 1 (echo    [失败] 返回码 !errorlevel! & set "FAIL=1") else (echo    [成功])
echo 停用 DSH_C3_Archive_1830 ...
schtasks /change /tn "DSH_C3_Archive_1830" /disable
if errorlevel 1 (echo    [失败] 返回码 !errorlevel! & set "FAIL=1") else (echo    [成功])
goto VERIFY

:ENABLE
echo.
echo 恢复 DSH_Run_2h ...
schtasks /change /tn "DSH_Run_2h" /enable
if errorlevel 1 (echo    [失败] 返回码 !errorlevel! & set "FAIL=1") else (echo    [成功])
echo 恢复 DSH_C3_Archive_1830 ...
schtasks /change /tn "DSH_C3_Archive_1830" /enable
if errorlevel 1 (echo    [失败] 返回码 !errorlevel! & set "FAIL=1") else (echo    [成功])
goto VERIFY

:VERIFY
echo.
echo 结果复查：
call :SHOW
if defined FAIL (
  echo.
  echo [提示] 有条目失败。备用办法：在「任务计划程序库」根下找到 DSH_Run_2h，
  echo        右键 → 禁用。下面可以帮您直接打开任务计划程序。
  echo.
  choice /c YN /m "现在打开任务计划程序吗"
  if errorlevel 2 goto END
  start "" taskschd.msc
)
goto END

:SHOW
schtasks /query /tn "DSH_Run_2h" /fo LIST /v | findstr /i "任务名 下次运行时间 计划任务状态 TaskName Next"
schtasks /query /tn "DSH_C3_Archive_1830" /fo LIST /v | findstr /i "任务名 下次运行时间 计划任务状态 TaskName Next"
exit /b 0

:END
echo.
echo 说明：停用只是不再触发，不删除任务定义，随时可用本文件选 2 恢复。
echo 两枚任务的原始 XML 备份在：
echo   D:\Project\zhiguanAI\_analysis_tmp\bak_20261109_gov\
echo.
pause
