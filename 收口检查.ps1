# 收口后闸门（只读检查 · 不改任何文件）
# 用法：powershell -ExecutionPolicy Bypass -File .\收口检查.ps1
# 依据：《AI-开工入口》§二.6（2026-09-21 法师裁定 D47④）
# 缘起：09-19 L1 瘦身闸门当日即破——规则无强制检查点。本脚本把收口三件事变成"必然看见"。
# 退出码：0 = 收口要件齐；2 = 有告警项（补齐后再关窗，或向法师说明豁免理由）
# 注意：本脚本自身输出的判据亦须被核验（教训 7.1），勿把 [OK] 当"工作完成"。

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

$warn = 0
function Section($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Bad($m)  { Write-Host "[告警] $m" -ForegroundColor Yellow; $script:warn++ }

Write-Host "止观AI 收口后闸门（只读）" -ForegroundColor White

# ---------- 1. L1 同步（三同步第③步） ----------
Section "1. L1 是否需同步（距 00_当前状态.md 上次提交是否超 24h）"
$lastL1 = git log -1 --format='%ct' -- '00_当前状态.md'
if (-not $lastL1) { Bad "L1 无提交历史？" }
else {
    $ageH = [math]::Round((([int64][datetimeoffset]::UtcNow.ToUnixTimeSeconds()) - [int64]$lastL1) / 3600.0, 1)
    if ($ageH -gt 24) { Bad "L1 已 $ageH 小时未更新——若本窗口有实质进展，须更新 L1 属己行后提交（§二.6①）" }
    else { Ok "L1 上次提交距今 $ageH 小时，24h 内。" }
}

# ---------- 2. 决策日志回填 ----------
Section "2. 决策日志最大 D 编号（本轮法师裁定须回填 D47+，§二.6②）"
$dline = Select-String -LiteralPath '01_项目管理\止观AI项目分工与决策日志.md' -Pattern '\*\*D(\d+)' |
         ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Sort-Object -Descending | Select-Object -First 1
if ($dline) { Write-Host "当前决策日志最大编号 = D$dline —— 本窗口若含新裁定，应登记 D$($dline+1)（纯执行轮可跳过）" -ForegroundColor White }
else { Bad "决策日志读不到 D 编号" }

# ---------- 3. L1 头部超 300 字闸门 ----------
Section "3. L1 头部更新条目长度（09-19 闸门：收口记录超 300 字即入冷档）"
$L1 = [System.IO.File]::ReadAllLines('00_当前状态.md')
$overs = @()
for ($i = 0; $i -lt [Math]::Min(12, $L1.Count); $i++) {
    $x = $L1[$i]
    if ($x -match '^> (更新|前次更新)' -and $x.Length -gt 300) { $overs += "行$($i+1)（$($x.Length) 字）：$($x.Substring(0, [Math]::Min(42, $x.Length)))…" }
}
if ($overs.Count -eq 0) { Ok "头部 ≤12 行内无超 300 字更新条目。" }
else { $overs | ForEach-Object { Bad "超长未归档 $_" } }

# ---------- 4. 本轮提交卫生 ----------
Section "4. 本窗口提交卫生"
$last = git log -1 --format='%h %s'
Write-Host "HEAD = $last" -ForegroundColor DarkGray
$tr = git log -1 --format='%b'
foreach ($k in @('Session: ', 'Window: ', 'Model: ')) {
    if ($tr -match "(?m)^$k") { Ok "最新提交含 trailer $k" } else { Bad "最新提交缺 trailer $k（§二.3 六件套）" }
}
$dirty = @(git status --porcelain | Where-Object { $_ -match '^.[MD]' })
if ($dirty.Count -eq 0) { Ok "工作区无未提交的已跟踪文件改动。" }
else { Write-Host "[提示] 尚有 $($dirty.Count) 项已跟踪改动未提交——若是他窗口在途文件，按纪律④不代提交、只报告：" -ForegroundColor White; $dirty | ForEach-Object { Write-Host "  $_" } }

# ---------- 结论 ----------
Write-Host ""
if ($warn -gt 0) {
    Write-Host "结论：[收口未完] $warn 项告警。补齐后重跑本脚本；确属可豁免项（如纯执行轮无需 D 编号），在收口说明中写明理由。" -ForegroundColor Yellow
    exit 2
} else {
    Write-Host "结论：[收口要件齐] 可关窗/交付。" -ForegroundColor Green
    exit 0
}
