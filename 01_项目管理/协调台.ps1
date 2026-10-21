# 协调台快照器 —— 只读，现算现出，不落第二本台账
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File 01_项目管理\协调台.ps1
# 说明：本器只读源件（git／台账／待裁单／登记分片／值守片／定时任务），不写任何盘上的数；
#       -Write 时另存一份快照到 _analysis_tmp\，供交班贴用，不提交。
param([switch]$Write)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $root
$Git  = 'C:\Program Files\Git\bin\git.exe'
function G { & $Git -C $repo @args 2>$null }

$now = Get-Date
$o = New-Object System.Collections.Generic.List[string]
function L($s) { $o.Add($s) }

L ("# 协调台快照　{0}" -f $now.ToString('yyyy-MM-dd HH:mm:ss'))
L ""

# ── 一、我这一窗在这个钟点在做什么（机械拍与交接拍是否还活着）
L "## 一、机械面（自动件是否还活着）"
$tk = @(
  @{N='DSH_Flow_Tick';        D='机械拍（整点 :35 扫值守片出单）'},
  @{N='DSH_C3_Archive_1830';  D='C3 归档（一次性 18:30）'},
  @{N='DSH_Web_Wake_2h';      D='web 保活（每 2 小时探 48000）'}
)
foreach ($t in $tk) {
  $r = (schtasks /query /tn $t.N /fo LIST 2>&1) -join "`n"
  $st = if ($r -match '(?m)^\s*(?:Status|状态)\s*[:：]\s*(.+?)\s*$') { $Matches[1] } else { '未建/查不到' }
  $nx = if ($r -match '(?m)^\s*(?:Next Run Time|下次运行时间)\s*[:：]\s*(.+?)\s*$') { $Matches[1] } else { '—' }
  L ("- {0}：{1}；状态＝{2}；下次＝{3}" -f $t.N, $t.D, $st, $nx)
}
L ""

# ── 二、库（谁落了什么，只认在库节点）
L "## 二、库（乙级面：在库节点）"
$head = (G rev-parse --short HEAD)
$dirty = @(G status --porcelain).Count
$behind = (G rev-list --count '@{u}..HEAD')
$todayCommits = @(G log --since 'midnight' --format='%h %ad %s' --date=format:'%H:%M' --no-merges)
L ("- HEAD＝{0}；待推＝{1}；脏区行＝{2}；今日提交＝{3} 笔" -f $head, $behind, $dirty, $todayCommits.Count)
foreach ($c in ($todayCommits | Select-Object -First 5)) { L ("  - {0}" -f $c) }
L ""

# ── 三、窗（分工到位与否，看登记分片与台账末行）
L "## 三、窗（分工面）"
$shards = @(Get-ChildItem (Join-Path $root '登记分片') -File -Filter '*.md' | Sort-Object LastWriteTime)
L ("- 登记分片＝{0} 枚；最近三枚：" -f $shards.Count)
foreach ($s in ($shards | Select-Object -Last 3)) { L ("  - {0}　{1}" -f $s.Name, $s.LastWriteTime.ToString('MM-dd HH:mm')) }
$led = Join-Path $root '交接试跑_20261019\收口台账.md'
if (Test-Path $led) {
  $rows = @(Get-Content $led -Encoding UTF8 | Where-Object { $_ -match '^\|' -and $_ -notmatch '^\|\s*-{2,}' })
  L ("- 收口台账＝{0} 行表格；末三行（原样）：" -f $rows.Count)
  foreach ($r in ($rows | Select-Object -Last 3)) { L ("  - {0}" -f $r.Trim()) }
}
L ""

# ── 四、须您一句（活条）与待落
L "## 四、候字面"
$td = Join-Path $root '待裁单.md'
if (Test-Path $td) {
  $ls = [System.IO.File]::ReadAllText($td, [System.Text.Encoding]::UTF8) -split "`n"
  $live = @($ls | Where-Object { $_ -match '^\|\s*\*\*候编号' })
  $pend = @($ls | Where-Object { $_ -match '\|\s*待起\s*\|' })
  $done = @($ls | Where-Object { $_ -match '\*\*已落\*\*' })
  L ("- 活条＝{0} 条；已落＝{1} 项；仍「待起」＝{2} 项" -f $live.Count, $done.Count, $pend.Count)
  foreach ($x in $live) { L ("  - {0}" -f $x.Trim()) }
}
L ""

# ── 五、值守片与库外件
L "## 五、值守面与库外件"
$sh = @(Get-ChildItem $root -Recurse -File -Filter 'C3-值守-*.md' -ErrorAction SilentlyContinue)
$inRepo = 0
foreach ($s in $sh) { $p = $s.FullName.Replace("$repo\", '').Replace('\', '/'); if ((G ls-files -- $p)) { $inRepo++ } }
L ("- 值守片＝{0} 枚；在库＝{1}；库外＝{2}" -f $sh.Count, $inRepo, ($sh.Count - $inRepo))
$unt = @(G status --porcelain --ignored -- '01_项目管理/*.ps1')
L ("- 库外/被忽略脚本＝{0} 枚：" -f $unt.Count)
foreach ($u in $unt) { L ("  - {0}" -f $u) }
L ""
L "—— 本快照只读，未写任何盘上数；数都带尺名与时刻，不带就是印象。"

$text = ($o -join "`r`n")
Write-Output $text
if ($Write) {
  $dst = Join-Path $repo ('_analysis_tmp\协调台快照_' + $now.ToString('MMdd_HHmm') + '.md')
  New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
  [System.IO.File]::WriteAllText($dst, $text, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host ("`n[已存] " + $dst)
}
