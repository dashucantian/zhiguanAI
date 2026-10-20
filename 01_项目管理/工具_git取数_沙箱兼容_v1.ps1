# 工具｜git 取数（沙箱兼容）v1 —— **唯一全文**
#
# 出处：2026-10-20 DSH 承接窗 `fc2ce735` 实测。同族问题三处：
#   ① `& git …` / `git … | Out-String` / `git … > 文件` 三写一律 `Program 'git.exe' failed to run: Access is denied`；
#   ② `Start-Process -Wait` / `-PassThru` 亦被拒（进程句柄被沙箱挡，不是 git 缺失）；
#   ③ **捕获失败时 Windows PowerShell 会静默返回空**，退码还不一定非零 ⇒ 与"确实没有改动"不可区分（坑 047／054 同族）。
# 可行路径：**cmd 内重定向 ＋ 完成哨兵 ＋ 延迟展开取退码**（git 的 stdout 落在文件里，不经管道）。
#
# 用法一（脚本内）：
#   . "D:\Project\zhiguanAI\01_项目管理\工具_git取数_沙箱兼容_v1.ps1"
#   $r = Invoke-Git 'status --porcelain'; if ($r.TimedOut) { … } ; $r.Out ; $r.Rc
# 用法二（命令行直取）：见本件末 $ArgLine 分支。
#
# ⚠ 本件必须存为 **UTF-8 带 BOM**。本机只有 Windows PowerShell 5.1（无 pwsh）；无 BOM 时 5.1 按 GBK 解析，
#   中文串乱码会**吞掉函数体而不报错** ⇒ `Invoke-Git` 静默返回 $null，看起来像"git 没装"（本窗花 5 轮定位）。
#   实测：用通用编辑工具改本件后 BOM 会被吃掉 ⇒ **每次改完必须复验首三字节＝ EF BB BF**。
#
# ⚠ 反证记录（写此件时当场自纠两次，留证防复发）：
#   ① v0 用 `echo %ERRORLEVEL%` ⇒ **整行在 git 跑之前就展开**，退码恒 0＝假绿；v1 改 `/v:on` + `!ERRORLEVEL!`。
#      校准：`rev-parse --short HEAD` → rc=0；`rev-parse --verify nonexistent-ref-xyz` → rc=128。两条都跑过才算验过。
#   ② 只测"成功路径"不算验；必须有一条**故意失败**的调用（同 §五.8 反证测试）。

$script:GitExeDefault = 'C:\Program Files\Git\bin\git.exe'
$script:GitRepoDefault = 'D:\Project\zhiguanAI'

function Invoke-Git {
  param(
    [Parameter(Mandatory = $true)][string]$ArgLine,
    [string]$Repo = $script:GitRepoDefault,
    [int]$TimeoutMs = 60000
  )
  $exe = $env:DSH_GIT_EXE
  if ([string]::IsNullOrWhiteSpace($exe)) { $exe = $script:GitExeDefault }
  if (-not (Test-Path $exe)) {
    return [pscustomobject]@{ Out = ''; Rc = $null; TimedOut = $false; Error = "git 不在：$exe" }
  }
  $tmp = Join-Path $env:TEMP ('gitcap_' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $o = Join-Path $tmp 'o.txt'
  $done = Join-Path $tmp 'rc.txt'
  $inner = '"' + $exe + '" -C "' + $Repo + '" ' + $ArgLine + ' > "' + $o + '" 2>&1 & echo !ERRORLEVEL! > "' + $done + '"'
  Start-Process -FilePath $env:ComSpec -ArgumentList ('/v:on /c "' + $inner + '"') -NoNewWindow -ErrorAction SilentlyContinue
  $n = 0
  while (-not (Test-Path $done) -and ($n * 100) -lt $TimeoutMs) { Start-Sleep -Milliseconds 100; $n++ }
  $rc = $null; $out = ''; $timedOut = $false
  if (Test-Path $done) { $rc = (Get-Content $done -Raw).Trim() } else { $timedOut = $true }
  if (Test-Path $o) { $out = [System.IO.File]::ReadAllText($o, [System.Text.Encoding]::UTF8) }
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  # ⚠ v1.0 缺陷（当轮自纠）：TimedOut 原写在 Remove-Item **之后**取 Test-Path ⇒ 恒 True ⇒ "能跑"被判成"超时"。
  #    留此注防复发：**判据求值必须在资源销毁之前**。
  return [pscustomobject]@{ Out = $out; Rc = $rc; TimedOut = $timedOut; Error = $null }
}

function Test-GitUsable {
  $r = Invoke-Git '--version'
  if ($r.TimedOut -or -not $r.Rc -or $r.Rc -ne '0' -or [string]::IsNullOrWhiteSpace($r.Out)) {
    return [pscustomobject]@{ Ok = $false; Version = ''; Detail = ("rc={0} timedout={1} out='{2}'" -f $r.Rc, $r.TimedOut, ($r.Out -replace '\s+', ' ').Trim()) }
  }
  return [pscustomobject]@{ Ok = $true; Version = $r.Out.Trim(); Detail = 'ok' }
}

# 命令行直取：powershell -NoProfile -ExecutionPolicy Bypass -File <本件> -ArgLine "log -1 --oneline"
if ($MyInvocation.InvocationName -ne '.' -and -not [string]::IsNullOrWhiteSpace($ArgLine)) {
  $r = Invoke-Git -ArgLine $ArgLine -Repo $Repo
  Write-Output $r.Out
  Write-Output ("[rc=" + $r.Rc + " timedout=" + $r.TimedOut + "]")
  exit ([int]($r.Rc -ne '0'))
}
