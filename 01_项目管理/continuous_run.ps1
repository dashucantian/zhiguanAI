# 连续执行器 continuous_run.ps1 —— 每轮把"能自动做的"一次做完，把"要人判断的"列成待办
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File 01_项目管理\continuous_run.ps1 [-Quiet]
# 设计：①八步固定节律，每步都留读数；②只做安全动作（跑拍／推送／跑闸／盘数），不代改文档、不代裁；
#      ③本轮结果写状态件与日志，下一轮据此续跑；④锁文件防并发；⑤退出码只反映"是否有硬失败"。
param([switch]$Quiet)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $root
$Git  = 'C:\Program Files\Git\bin\git.exe'
$logDir = Join-Path $repo '_analysis_tmp'
$log = Join-Path $logDir 'continuous_run.log'
$stateFile = Join-Path $logDir 'continuous_state.json'
$lockFile = Join-Path $logDir 'continuous_run.lock'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function T { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }
function W($msg) {
  $line = '[' + (T) + '] ' + $msg
  Add-Content -Path $log -Value $line -Encoding UTF8
  if (-not $Quiet) { Write-Host $line }
}
function G { & $Git -C $repo @args 2>$null }

# ── 锁（防两轮并发）
if (Test-Path $lockFile) {
  $age = (Get-Date) - (Get-Item $lockFile).LastWriteTime
  if ($age.TotalMinutes -lt 25) { W ('ABORT 上一轮仍在跑（锁 ' + [int]$age.TotalMinutes + ' 分钟）'); exit 0 }
  Remove-Item $lockFile -Force
}
Set-Content -Path $lockFile -Value (T) -Encoding UTF8

$prev = $null
if (Test-Path $stateFile) { try { $prev = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $prev = $null } }
$r = [ordered]@{ runAt = (T); steps = @(); flags = @(); hardFail = 0; lastFullGate = $(if ($prev) { $prev.lastFullGate } else { $null }) }

function Step($no, $name, $body) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $res = ''
  try { $res = [string](& $body) } catch { $res = 'ERR ' + $_.Exception.Message; $r.hardFail++ }
  $sw.Stop()
  $r.steps += [pscustomobject]@{ no = $no; name = $name; ms = $sw.ElapsedMilliseconds; result = $res }
  W ('S' + $no + ' ' + $name + '：' + $res + '（' + $sw.ElapsedMilliseconds + 'ms）')
}

# ── S1 拉源（只读日志末行，取不到即"未检"）
Step 1 '拉源' {
  $p = Join-Path $root '任务关系图\源表早晚校验日志.txt'
  if (-not (Test-Path $p)) { $r.flags += '源表日志缺→未检'; return '未检（日志缺）' }
  $t = (Get-Content $p -Encoding UTF8 -Tail 1)
  if ($t -match '(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') { $r.flags += ('源表末拍 ' + $Matches[1]) }
  if ($t -match '(\d+)行') { return ('末拍 ' + $Matches[1] + ' 行') }
  return '末行已读（未解析出行数）'
}

# ── S2 盘片（跑机械拍，幂等）
Step 2 '盘片' {
  $p = Join-Path $root 'flow_tick.ps1'
  if (-not (Test-Path $p)) { $r.flags += 'flow_tick 缺'; return '未检（脚本缺）' }
  $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $p 2>&1
  $last = (Get-Content (Join-Path $logDir 'flow_tick.log') -Encoding UTF8 -Tail 3) -join ' / '
  if ($last -match '本拍落 (\d+) 枚') { return ('落 ' + $Matches[1] + ' 枚') }
  if ($last -match '本拍无活') { return '无活' }
  return '已跑（' + ($out | Select-Object -Last 1) + '）'
}

# ── S3 盘库（分类，不 add）
Step 3 '盘库' {
  $st = @(G status --porcelain)
  $box = @(G status --porcelain -- '01_项目管理/交接试跑_20261019/DSH-fc2ce735')
  $r.flags += ('脏区 ' + $st.Count + ' 行（本窗盒内 ' + $box.Count + '）')
  return ('脏区 ' + $st.Count + '／盒内 ' + $box.Count)
}

# ── S4 入库（只补登出单件；其他一律交给人工）
Step 4 '入库' {
  $box = @(G status --porcelain -- '01_项目管理/交接试跑_20261019/DSH-fc2ce735')
  if ($box.Count -eq 0) { return '无可自动入库件' }
  $r.flags += ('盒内待入库 ' + $box.Count + ' 件→已交 S4（机械拍补登）')
  return ('盒内 ' + $box.Count + ' 件（机械拍补登负责）')
}

# ── S5 推
Step 5 '推' {
  $ahead = (G rev-list --count '@{u}..HEAD')
  if ([int]$ahead -eq 0) { return '无待推' }
  $env:GIT_SSH_COMMAND = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20'
  G push origin HEAD:master | Out-Null
  $left = (G rev-list --count '@{u}..HEAD')
  if ([int]$left -gt 0) { $r.flags += '推送后仍有待推 ' + $left; $r.hardFail++; return ('推送失败，余 ' + $left) }
  return ('推完 ' + $ahead + ' 笔，余 0')
}

# ── S6 闸（两件同跑）
Step 6 '闸' {
  $g1 = Join-Path $root '交接面检查.ps1'
  $g2 = Join-Path $repo '收口检查.ps1'
  $r1 = 0; $r2 = 0
  $dueFull = $true
  if ($r.lastFullGate) { try { $dueFull = (((Get-Date) - [datetime]$r.lastFullGate).TotalHours -ge 6) } catch { $dueFull = $true } }
  if (Test-Path $g1) { & powershell -NoProfile -ExecutionPolicy Bypass -File $g1 2>&1 | Out-Null; $r1 = $LASTEXITCODE }
  if ((Test-Path $g2) -and $dueFull) { $o = (& powershell -NoProfile -ExecutionPolicy Bypass -File $g2 2>&1) -join "`n"; $r2 = $LASTEXITCODE; $r.lastFullGate = (T)
    if ($o -match '结论：\[([^\]]+)\]') { $r.flags += ('主闸：' + $Matches[1]) }
    if ($o -match '(\d+) 项告警') { $r.flags += ('主闸告警 ' + $Matches[1] + ' 项') } }
  if ($r1 -ne 0) { $r.hardFail++ }
  if (-not $dueFull) { return ('交接面 rc=' + $r1 + '／主闸本轮跳过（距上次整跑未满 6 小时；上次 ' + $r.lastFullGate + '）') }
  return ('交接面 rc=' + $r1 + '／主闸 rc=' + $r2)
}

# ── S7 验收与候字（报数不改页）
Step 7 '验收' {
  $td = Join-Path $root '待裁单.md'
  $live = 0
  if (Test-Path $td) { $live = @((Get-Content $td -Encoding UTF8) | Where-Object { $_ -match '^\|\s*\*\*候编号' }).Count }
  if ($live -gt 0) { $r.flags += ('候字 ' + $live + ' 条') }
  return ('活条 ' + $live + ' 条')
}

# ── S8 对账（四面交叉，写状态件）
Step 8 '对账' {
  $shard = @(G ls-files -- '01_项目管理/登记分片/C3-值守-*.md').Count
  $order = @(G ls-files -- '01_项目管理/交接试跑_20261019/DSH-fc2ce735/*待提交单*').Count
  $head  = (G rev-parse --short HEAD)
  $led   = Join-Path $root '交接试跑_20261019\收口台账.md'
  $ledRows = 0
  if (Test-Path $led) { $ledRows = @((Get-Content $led -Encoding UTF8) | Where-Object { $_ -match '^\|' }).Count }
  return ('片在库 ' + $shard + '／单在库 ' + $order + '／台账 ' + $ledRows + ' 行／HEAD ' + $head)
}

Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
$r.runAt = (T)
$r | ConvertTo-Json -Depth 5 | Set-Content -Path $stateFile -Encoding UTF8
W ('== 本轮结束：硬失败 ' + $r.hardFail + '；待办 ' + $r.flags.Count + ' 项 ==')
if (-not $Quiet) {
  Write-Host ''
  Write-Host '本轮待办（要人或要字）：'
  $r.flags | ForEach-Object { Write-Host ('  • ' + $_) }
}
exit ([int]($r.hardFail -gt 0))
