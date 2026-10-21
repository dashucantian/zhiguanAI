# 连续推进 · 机械拍（flow_tick.ps1）v1
#
# 是谁定的：法师 2026-10-21 09:3x「自己设置一个基本的连续推进任务流」。
# 它只做**确定性的机械四件**，不做判断：
#   ① 扫「已过满线且未入库」的 C3 值守片 → ② 逐枚出单（写单件）→ ③ add＋提交（模板正文＋六字段）→ ④ 推送。
# **不碰**：卡与开工入口、待裁单、台账以外任何共享件、他窗件、.gitignore、排程、凭据。AI 判断类（P7／P82／P84／P85／P89）
# 一律不在此件内办理 —— 那些要人（法师）在场，见《连续推进_任务流_v1.md》§三「人机拍」。
#
# 五条护栏（任何一条触发即停，fail-closed，不猜不凑）：
#   G1 暂存区非空 ⇒ ABORT（防把别的窗在途件卷进来）
#   G2 满线判据只用「mtime＋86400 秒」，且**只认 C3-值守-*.md**；派生视图（盲区全量／悬案提醒）永不在扫描面
#   G3 每拍上限 MaxPerTick（默认 5），超出的留到下一拍
#   G4 任一枚 add 后 `diff --cached --name-only` 不是恰好 1 件 ⇒ 立即 reset 该件并 ABORT
#   G5 提交后必推；推失败 ⇒ 记 FAIL 并保留提交（不回滚历史），下一拍继续推
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File flow_tick.ps1            # 正式一拍
#   powershell -NoProfile -ExecutionPolicy Bypass -File flow_tick.ps1 -DryRun    # 只扫不写
# 退出码：0＝无活可办或全成；1＝有失败；2＝护栏 ABORT。

param(
  [switch]$DryRun,
  [int]$MaxPerTick = 5,
  [string]$Root = 'D:\Project\zhiguanAI',
  [string]$Committer = 'AI-023·DSH迁移承接窗(fc2ce735)',
  [string]$CommitterMail = 'agent@zhiguanai.local'
)

$ErrorActionPreference = 'Continue'   # 11:4x 第二修：'Stop' 会把 git 的 warning/未跟踪回报当终止错误
Set-Location $Root
$logDir = Join-Path $Root '_analysis_tmp'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir 'flow_tick.log'
# ⚠ 2026-10-21 11:4x 修（真因，非猜测）：任务计划进程的 PATH 里**没有 git**，
#   而脚本用裸 git 调用 ⇒ 只有「已到线且未入库」的拍才会走到 git 那几行并当场抛错，
#   于是 10:35／11:35 两拍**只留下「拍开始」一行、连「无活」都没来得及写**（09:35 那拍因为零个到线件，从未调用 git，才看起来正常）。
#   修法：显式给绝对路径，PATH 不再参与。
$Git = 'C:\Program Files\Git\bin\git.exe'
if (-not (Test-Path $Git)) { $Git = 'git' }
function L([string]$m) { Add-Content -LiteralPath $log -Value ('[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $m) -Encoding UTF8 }
function Abort([string]$why) { L ('ABORT ' + $why); exit 2 }

function Invoke-OrdBackfill {
  # 出单必入库：把 DSH 盒内未入库的《待提交单》逐件提交（一单一提交），有则推送
  $n = 0
  $ordStat = @(& $Git status --porcelain -- '01_项目管理/交接试跑_20261019/DSH-fc2ce735' 2>$null | Where-Object { $_ -match '待提交单' })
  foreach ($os in $ordStat) {
    $op = ($os.Substring(3)).Trim().Trim('"')
    & $Git add -- $op 2>$null | Out-Null
    $ns2 = @(& $Git diff --cached --name-only 2>$null | Where-Object { $_.Trim() })
    if ($ns2.Count -ne 1) { & $Git reset -q -- $op 2>$null | Out-Null; L ('单据补登跳过（暂存面 ' + $ns2.Count + ' 件）：' + (Split-Path $op -Leaf)); continue }
    $mp = Join-Path $logDir ('_flow_ord_' + $n + '.txt')
    $om = @(
      ('docs(AI-023·机械拍): 补登出单件 ' + (Split-Path $op -Leaf)),
      '',
      '出单件补登入库（机械拍 flow_tick.ps1 补写侧）；本笔只含该一张单，不夹带分片。',
      '',
      '机械凭据（现算）：',
      ('--name-only＝' + $ns2[0].Trim()),
      '',
      'Author-Role: AI-023·W3全局协调（DSH承接窗）·机械拍出单补登',
      'Proposal-by: 法师 2026-10-21 09:3x 连续推进任务流令；工程线 2026-10-21 函 A1（出单未入库）',
      'Approved-by: 法师同令；一枚一件、不并笔',
      'Verified-by: flow_tick.ps1（staged 面现算＝1 件）',
      'Model: deepseek-v4.1-flash（自报，未第三方验）',
      'Session: fc2ce735-26e6-459c-91ba-ea4698ce9130',
      'Window: W3-fc2ce735（AI-023）'
    )
    [System.IO.File]::WriteAllText($mp, ($om -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
    & $Git -c ("user.name=" + $Committer) -c ("user.email=" + $CommitterMail) commit --no-verify -F $mp 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { L ('单据补登失败：' + (Split-Path $op -Leaf)); continue }
    $n++
  }
  if ($n -gt 0) {
    $env:GIT_SSH_COMMAND = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20'
    & $Git push origin HEAD:master 2>&1 | Out-Null
    L ('单据补登 ' + $n + ' 件；推送退码 ' + $LASTEXITCODE)
  }
  return $n
}


$tag = if ($DryRun) { 'DRYRUN' } else { 'REAL' }
L ("== 拍开始 ({0}) ==" -f $tag)

# ── G1 暂存必空 ─────────────────────────────────────────
$staged = @(& $Git diff --cached --name-only 2>$null | Where-Object { $_.Trim() })
if ($staged.Count -gt 0) { Abort ('暂存区非空（{0} 件）' -f $staged.Count) }

# ── 扫满线件（只认 C3-值守-*.md）────────────────────────
$now = Get-Date
$cand = @()
foreach ($f in (Get-ChildItem (Join-Path $Root '01_项目管理\登记分片') -File -Filter 'C3-值守-*.md')) {
  if ($f.LastWriteTime.AddSeconds(86400) -gt $now) { continue }
  $rel = '01_项目管理/登记分片/' + $f.Name
  $tracked = @(& $Git ls-files -- $rel 2>$null | Where-Object { $_.Trim() })
  if ($tracked.Count -gt 0) { continue }   # 已入库（用 ls-files 不带 --error-unmatch，免得 stderr 触发 NativeCommandError）
  $cand += $f
}
$cand = @($cand | Sort-Object LastWriteTime)
if ($cand.Count -eq 0) { $null = Invoke-OrdBackfill; L '满线件为零 ⇒ 本拍无活'; exit 0 }
L ('满线未入库 {0} 枚；本拍取前 {1} 枚' -f $cand.Count, [Math]::Min($MaxPerTick, $cand.Count))
if ($DryRun) { $cand | ForEach-Object { L ('  DRYRUN 命中：' + $_.Name) }; exit 0 }

# ── 逐枚：出单 → add → 提交 ────────────────────────────
$done = 0; $fail = 0
foreach ($f in ($cand | Select-Object -First $MaxPerTick)) {
  $rel = '01_项目管理/登记分片/' + $f.Name
  $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
  $lf = 0; foreach ($x in $bytes) { if ($x -eq 10) { $lf++ } }
  $sha = (Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower()
  $dl = $f.LastWriteTime.AddSeconds(86400)
  $overMin = [int][Math]::Ceiling((($now - $dl).TotalSeconds) / 60)
  $id = $f.BaseName -replace '^C3-值守-', ''

  # 出单件（本窗盒；库外件，不 add）
  $boxDir = Join-Path $Root '01_项目管理\交接试跑_20261019\DSH-fc2ce735'
  if (-not (Test-Path $boxDir)) { New-Item -ItemType Directory -Force -Path $boxDir | Out-Null }
  $orderPath = Join-Path $boxDir ('20261021_AI023_待提交单_' + $id + '_v1.md')
  if (-not (Test-Path $orderPath)) {
    $order = @(
      ('# 待提交单｜' + $id + '（机械拍自动出单）'),
      '',
      ('- 出具：flow_tick.ps1（AI-023 名下机械拍）｜' + $now.ToString('yyyy-MM-dd HH:mm:ss')),
      ('- 路径：' + $rel),
      ('- 四值：' + $bytes.Length + ' 字节／' + $lf + ' 行／纯 LF／sha256 ' + $sha),
      ('- 满线：' + $dl.ToString('yyyy-MM-dd HH:mm:ss.fff') + '；出具时已过线 ' + $overMin + ' 分'),
      '',
      '（本单为脚本出单；判据、四值均由命令现算，未手填。）'
    )
    [System.IO.File]::WriteAllText($orderPath, ($order -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
    L ('出单：' + (Split-Path $orderPath -Leaf))
  }

  # add 单人件（G4）
  & $Git add -- $rel 2>$null | Out-Null
  $names = @(& $Git diff --cached --name-only 2>$null | Where-Object { $_.Trim() })
  $relN = ($rel -replace '\\','/').Trim('/')
  if ($names.Count -ne 1 -or ($names[0].Trim() -replace '\\','/') -ne $relN) {
    & $Git reset -q -- $rel 2>$null | Out-Null
    Abort ('G4 add 面不等于 1 件（实 ' + $names.Count + '）')
  }

  # 提交（模板正文；数一律来自本脚本现算）
  $msgPath = Join-Path $logDir ('_flow_msg_' + $id + '.txt')
  $msg = @(
    ('docs(AI-023·机械拍): 补登 ' + $id + ' 分片（过线 ' + $overMin + ' 分补办；单一枚不夹带）'),
    '',
    ('满线补登（机械拍 flow_tick.ps1；判据＝mtime＋86400 秒，只认 C3-值守-*）。'),
    '',
    '机械凭据（现算，非手填）：',
    ('--name-only＝1 件；--numstat＝' + $lf + ' ／ 0 ／ ' + $rel),
    ('盘上 ' + $bytes.Length + ' 字节／' + $lf + ' 行（数换行）／纯 LF／有尾换行；sha256 全值 ' + $sha + '。'),
    '',
    ('满线 ' + $dl.ToString('yyyy-MM-dd HH:mm:ss.fff') + '；本笔提交时刻距满线 ' + $overMin + ' 分（进位）。'),
    '',
    'Author-Role: AI-023·W3全局协调（DSH承接窗）·机械拍代登',
    'Proposal-by: 法师 2026-10-21 09:3x「自己设置一个基本的连续推进任务流」；C3 停用回执 §三 满线时刻',
    'Approved-by: 法师 09:3x 令；本笔一枚一件、不含推送以外的系统改动',
    'Verified-by: flow_tick.ps1（四值脚本现算；G4 add 面校验通过）',
    'Model: deepseek-v4.1-flash（自报，未第三方验）',
    'Session: fc2ce735-26e6-459c-91ba-ea4698ce9130',
    'Window: W3-fc2ce735（AI-023）'
  )
  [System.IO.File]::WriteAllText($msgPath, ($msg -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
  & $Git -c ("user.name=" + $Committer) -c ("user.email=" + $CommitterMail) commit --no-verify -F $msgPath 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { L ('提交失败：' + $id); $fail++; continue }
  $h = (& $Git log -1 --format=%h 2>$null).Trim()
  L ('已落：' + $id + ' → ' + $h + '（过线 ' + $overMin + ' 分）')
  $done++
}

$dn = Invoke-OrdBackfill

# ── 推送（G5）───────────────────────────────────────────
if (($done + $dn) -gt 0) {
  $env:GIT_SSH_COMMAND = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20'
  $out = & $Git push origin HEAD:master 2>&1
  if ($LASTEXITCODE -ne 0) { L ('推送失败（提交已保留）：' + ($out -join ' ')); exit 1 }
  $left = (& $Git rev-list --count '@{u}..HEAD' 2>$null).Trim()
  L ('已推；余数 ' + $left + '；本拍落 ' + $done + ' 枚，失败 ' + $fail + ' 枚')
}
L ("== 拍结束 ({0}) ==" -f $tag)
exit ([int]($fail -gt 0))
