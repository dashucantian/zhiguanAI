@echo off
chcp 65001 >nul
setlocal
set "PAT="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$s=Read-Host '请粘贴 Qoder 个人访问令牌（输入不显示）' -AsSecureString; $p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)"`) do set "PAT=%%i"
if not defined PAT (
  echo 没有输入，没有设。
  goto :fin
)
setx QODERCN_PERSONAL_ACCESS_TOKEN "%PAT%" >nul
echo 已设好用户级环境变量 QODERCN_PERSONAL_ACCESS_TOKEN。
echo 令牌只在系统环境变量里，不落盘、不进日志。
echo 已经开着的桥不会自动读到它，要重新起一次桥（双击 启动Qoder窗口桥.cmd）。
:fin
echo.
pause
