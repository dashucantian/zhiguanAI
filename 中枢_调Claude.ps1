<#
.SYNOPSIS
  中枢_调Claude.ps1 — 以只读方式调用 Claude 窗（Claude Code CLI / Opus 级模型）做判读。

.DESCRIPTION
  用途：把「人工转贴只读包给 AI-027」升级为「中枢一次调用、产出落盘」。
  授权：法师 2026-11-01 14:0x 准「按三级出网调用」＋「把命令固化成脚本」。
  纪律：
    - 工具白名单只有 Read/Grep/Glob ⇒ 只读由工具集强制，不靠模型自觉（判语 033）。
    - 显式 disallow Bash/Write/Edit/MultiEdit/NotebookEdit/Task/WebFetch/WebSearch。
    - cwd 钉死在本仓根；输出只落 _analysis_tmp\claude_calls。
    - 每次调用记一行八段日志（含 level=L3_EGRESS｜三级出网）。
    - 不打印、不落盘任何密钥；不自动提交。

.PARAMETER Prompt
  直接给提示词（≤8 KB；超了改用 -PromptFile）。

.PARAMETER PromptFile
  提示词文件（仓内相对路径或绝对路径）；脚本让 Claude 自己读该文件，避免命令行长限制。

.PARAMETER Model
  可选，透传 --model。

.PARAMETER TimeoutSec
  硬超时，默认 300 秒；超时杀进程并退 124。

.PARAMETER DryRun
  只打印将要执行的命令行，不调模型（不产生任何出网）。

.NOTES
  退出码：0 成功｜2 参数／环境错｜3 未登录｜4 可执行缺失｜5 提示词过大｜124 超时｜其余＝CLI 原退码。
#>
[CmdletBinding(DefaultParameterSetName = 'Text')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Text')]
    [string]$Prompt,

    [Parameter(Mandatory = $true, ParameterSetName = 'File')]
    [string]$PromptFile,

    [string]$Model = '',
    [int]$TimeoutSec = 300,
    [string]$OutDir = '',
    [string]$TaskId = 'TASK-20261101-02',
    [string]$Approver = '宗国法师',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$exeCandidates = @(
    $env:CLAUDE_EXE,
    (Join-Path $env:LOCALAPPDATA 'Claude-3p\claude-code\2.1.309\9078b9c1d466\claude.exe')
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $exeCandidates) {
    [Console]::Error.WriteLine('找不到 claude.exe（可设 CLAUDE_EXE 指定）。退码 4。')
    exit 4
}
$exe = @($exeCandidates)[0]

# ---- 代理：Node／CLI 不读 Windows 系统代理，必须显式传给子进程 ----
# 实测（2026-11-01）：直连 api.anthropic.com 得 403；走 127.0.0.1:10808 得 405（Anthropic 真回）⇒ 代理通、CLI 未用。
$proxyEnv = @{}
if (-not $env:HTTPS_PROXY -and -not $env:https_proxy) {
    try {
        $inet = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
        if ($inet.ProxyEnable -eq 1 -and $inet.ProxyServer) {
            $srv = [string]$inet.ProxyServer
            $p = $null
            if ($srv -match '=') {
                foreach ($part in ($srv -split ';')) {
                    $kv = $part -split '=', 2
                    if ($kv.Count -eq 2 -and $kv[0].Trim() -eq 'https') { $p = $kv[1].Trim(); break }
                }
            }
            if (-not $p) { $p = ($srv -split ';')[0].Trim() }
            if ($p -and $p -notmatch '^[a-z]+://') { $p = "http://$p" }
            if ($p) {
                $proxyEnv['HTTPS_PROXY'] = $p
                $proxyEnv['HTTP_PROXY'] = $p
                $proxyEnv['NO_PROXY'] = '127.0.0.1,localhost'
            }
        }
    } catch { }
}

if (-not $OutDir) { $OutDir = Join-Path $repo '_analysis_tmp\claude_calls' }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

# ---- 提示词 ----
if ($PSCmdlet.ParameterSetName -eq 'Text') {
    $promptText = $Prompt
    if ([Text.Encoding]::UTF8.GetByteCount($promptText) -gt 8192) {
        [Console]::Error.WriteLine('提示词超过 8 KB；请改用 -PromptFile 让 Claude 自己读文件。退码 5。')
        exit 5
    }
} else {
    $pf = if ([IO.Path]::IsPathRooted($PromptFile)) { $PromptFile } else { Join-Path $repo $PromptFile }
    if (-not (Test-Path $pf)) { [Console]::Error.WriteLine("提示词文件不存在：$pf（退码 2）"); exit 2 }
    $promptText = "先读这个文件（用 Read 工具）：$pf`n`n然后按文件里的要求作答；只回发现清单与结论，不要改任何文件。"
}

# ---- 参数：只读工具集 ----
$allow = 'Read,Grep,Glob'
$deny = 'Bash,Write,Edit,MultiEdit,NotebookEdit,Task,WebFetch,WebSearch'
$argv = @('-p', '--allowedTools', $allow, '--disallowedTools', $deny, '--output-format', 'text')
if ($Model) { $argv += @('--model', $Model) }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outFile = Join-Path $OutDir "claude-$stamp.md"

Write-Host ("[plan] cwd={0}" -f $repo)
Write-Host ("[plan] exe={0}" -f $exe)
Write-Host ("[plan] allow={0}" -f $allow)
Write-Host ("[plan] deny={0}" -f $deny)
Write-Host ("[plan] prompt={0} 字符" -f $promptText.Length)
Write-Host ("[plan] proxy={0}" -f $(if ($proxyEnv.Count) { $proxyEnv['HTTPS_PROXY'] } elseif ($env:HTTPS_PROXY) { $env:HTTPS_PROXY } else { 'none（直连）' }))
Write-Host ("[plan] out={0}" -f $outFile)

if ($DryRun) {
    Write-Host '[plan] DryRun：未调用模型，无出网。'
    exit 0
}

# ---- 启动（.NET Process：stdin 传提示、异步收流、可强杀） ----
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.Arguments = ($argv | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
$psi.WorkingDirectory = $repo
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.RedirectStandardInput = $true
$psi.StandardOutputEncoding = [Text.Encoding]::UTF8
$psi.StandardErrorEncoding = [Text.Encoding]::UTF8
$psi.EnvironmentVariables['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
foreach ($k in $proxyEnv.Keys) { $psi.EnvironmentVariables[$k] = $proxyEnv[$k] }

$sw = [Diagnostics.Stopwatch]::StartNew()
$proc = [Diagnostics.Process]::Start($psi)
try { $proc.StandardInput.Write($promptText); $proc.StandardInput.Close() } catch { }

$outTask = $proc.StandardOutput.ReadToEndAsync()
$errTask = $proc.StandardError.ReadToEndAsync()
$finished = $proc.WaitForExit($TimeoutSec * 1000)

if (-not $finished) {
    try { $proc.Kill() } catch { }
    $sw.Stop()
    $elapsed = [int]$sw.Elapsed.TotalMilliseconds
    Write-Host ("task={0} time={1} channel=claude-cli action=review http=none summary=timeout level=L3_EGRESS approver={2} target=local-cli elapsed_ms={3}" -f `
        $TaskId, (Get-Date).ToString('s'), $Approver, $elapsed)
    [Console]::Error.WriteLine("调用超时（>$TimeoutSec 秒），已杀进程。退码 124。")
    exit 124
}

$stdout = $outTask.GetAwaiter().GetResult()
$stderr = $errTask.GetAwaiter().GetResult()
$rc = $proc.ExitCode
$sw.Stop()
$elapsed = [int]$sw.Elapsed.TotalMilliseconds

$combined = ($stdout + "`n" + $stderr)
$notLoggedIn = $combined -match 'Not logged in|Please run /login'
$summary = if ($notLoggedIn) { 'not-logged-in' } elseif ($rc -eq 0) { 'ok' } else { "rc=$rc" }

Write-Host ("task={0} time={1} channel=claude-cli action=review http=none summary={2} level=L3_EGRESS approver={3} target=local-cli elapsed_ms={4}" -f `
    $TaskId, (Get-Date).ToString('s'), $summary, $Approver, $elapsed)

$body = @(
    "# Claude 调用记录 $stamp",
    "",
    "- 任务：$TaskId｜级别：**L3_EGRESS（三级出网）**｜审批：$Approver",
    "- 可执行：``$exe``",
    "- cwd：``$repo``",
    "- 工具白名单：``$allow``；禁用：``$deny``",
    "- 退码：$rc｜耗时：$elapsed ms｜超时上限：$TimeoutSec s",
    "- 提示词：",
    "",
    '```text',
    $promptText,
    '```',
    "",
    "## 输出",
    "",
    '```text',
    $stdout.Trim(),
    '```'
)
if ($stderr.Trim()) {
    $body += @("", "## 标准错误", "", '```text', $stderr.Trim(), '```')
}
[IO.File]::WriteAllText($outFile, ($body -join "`r`n"), (New-Object Text.UTF8Encoding($false)))
Write-Host ("[out] {0}" -f $outFile)

if ($notLoggedIn) {
    Write-Host '[hint] CLI 未登录：请在 Claude Desktop 侧或命令行执行一次 /login（或 claude setup-token），然后重跑本脚本。退码 3。'
    exit 3
}

exit $rc
