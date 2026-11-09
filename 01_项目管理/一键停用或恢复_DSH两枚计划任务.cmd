@echo off
setlocal EnableExtensions EnableDelayedExpansion
title 止观AI｜本机常驻任务：停用与恢复（5 枚）
color 0F

echo ==========================================================
echo   止观AI｜本机常驻任务：停用 / 恢复
echo   1 DSH_Run_2h              每 2 小时跑连续执行器并推整个工作区
echo   2 DSH_C3_Archive_1830    10-21 已跑完的一次性归档任务
echo   3 DSH_Web_Wake_2h        每 2 小时把 DSH 网页（48000）拉起来
echo   4 AI调用管家代理          每分钟保活本机 AI 路由（8791）
echo   5 AI调用管家看门狗        每 5 分钟看住代理
echo ==========================================================
echo.

net session >nul 2>&1
if errorlevel 1 goto NEEDADMIN

:ADMIN
echo 当前状态：
call :SHOW
echo.
echo 请选择：
echo   1 = 停 DSH 两枚历史件（Run_2h / C3_Archive_1830）
echo   2 = 停 网页自启（DSH_Web_Wake_2h）
echo   3 = 停 AI 调用管家两枚（代理 / 看门狗）
echo   4 = 恢复全部五枚
echo   0 = 取消
echo.
set "CH="
set /p "CH=输入序号后回车 = "
if "%CH%"=="1" goto STOPDSH
if "%CH%"=="2" goto STOPWEB
if "%CH%"=="3" goto STOPROUTER
if "%CH%"=="4" goto ENABLEALL
echo 已取消，未改动任何东西。
goto END

:NEEDADMIN
echo 需要管理员权限，正在提权，请在弹出的窗口点「是」...
echo （若没有弹窗，请右键本文件选「以管理员身份运行」）
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b 0

:STOPDSH
call :OFF "DSH_Run_2h"
call :OFF "DSH_C3_Archive_1830"
goto VERIFY

:STOPWEB
call :OFF "DSH_Web_Wake_2h"
goto VERIFY

:STOPROUTER
echo   注意：本机 AI 路由 8791 现在在跑，停这两枚只是不再保活；
echo         路由进程若退出，以后要手动启动（启动代理.cmd）。
call :OFF "AI调用管家代理"
call :OFF "AI调用管家看门狗"
goto VERIFY

:ENABLEALL
call :ON "DSH_Run_2h"
call :ON "DSH_C3_Archive_1830"
call :ON "DSH_Web_Wake_2h"
call :ON "AI调用管家代理"
call :ON "AI调用管家看门狗"
goto VERIFY

:VERIFY
echo.
echo 结果复查：
call :SHOW
if defined FAIL (
  echo.
  echo [提示] 有条目失败。备用办法：Win+R 输入 taskschd.msc 回车，
  echo        在「任务计划程序库」根下找到同名任务，右键 → 禁用 / 启用。
  echo.
  choice /c YN /m "现在打开任务计划程序吗"
  if errorlevel 2 goto END
  start "" taskschd.msc
)
goto END

:SHOW
for %%T in ("DSH_Run_2h" "DSH_C3_Archive_1830" "DSH_Web_Wake_2h" "AI调用管家代理" "AI调用管家看门狗") do (
  echo   --- %%~T
  schtasks /query /tn "%%~T" /fo LIST /v | findstr /i "计划任务状态 下次运行时间"
)
exit /b 0

:OFF
schtasks /change /tn "%~1" /disable >nul 2>&1
if errorlevel 1 (echo    [失败] %~1 & set "FAIL=1") else (echo    [已停] %~1)
exit /b 0

:ON
schtasks /change /tn "%~1" /enable >nul 2>&1
if errorlevel 1 (echo    [失败] %~1 & set "FAIL=1") else (echo    [已恢复] %~1)
exit /b 0

:END
echo.
echo 说明：停用只是不再触发，不删除任务定义，随时可用本文件恢复。
echo 停「网页自启」不影响已经在跑的网页；停「AI 调用管家」不影响已在跑的路由进程。
echo.
pause
