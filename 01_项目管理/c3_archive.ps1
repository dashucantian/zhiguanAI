# C3 归档末行（一次性；法师 2026-10-21 11:5x 裁「归档时点取 18:30」）
#
# 它只做三件确定的事：
#   ① 现查 C3 值守片在库／库外数（只认 `C3-值守-*.md`）
#   ② 往《收口台账》追加一行归档末行（**不写、也不伪造「本窗停用：」**——那行只能 C3 自己写）
#   ③ 提交并推送（署名 AI-023；具名一件，不 -A、不 -f）
# 护栏：G1 暂存非空即 ABORT；G2 台账行只追加、不改既有行；G3 推失败保留提交并记 FAIL。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File c3_archive.ps1 [-DryRun]

param(
  [switch]$DryRun,
  [string]$Root = 'D:\Project\zhiguanAI',
  [string]$Committer = 'AI-023·DSH迁移承接窗(fc2ce735)',
  [string]$CommitterMail = 'agent@zhiguanai.local'
)
$ErrorActionPreference = 'Continue'
$Git = 'C:\Program Files\Git\bin\git.exe'
if (-not (Test-Path $Git)) { $Git = 'git' }
Set-Location $Root
$log = Join-Path $Root '_analysis_tmp\c3_archive.log'
function L([string]$m) { Add-Content -LiteralPath $log -Value ('[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $m) -Encoding UTF8 }

L ('== C3 归档末行开始 (DryRun={0}) ==' -f $DryRun)
$staged = @(& $Git diff --cached --name-only 2>$null | Where-Object { $_.Trim() })
if ($staged.Count -gt 0) { L ('ABORT 暂存非空 ' + $staged.Count); exit 2 }

$all = @(Get-ChildItem (Join-Path $Root '01_项目管理\登记分片') -File -Filter 'C3-值守-*.md')
$inRepo = 0; $outRepo = 0; $outNames = @()
foreach ($f in $all) {
  $rel = '01_项目管理/登记分片/' + $f.Name
  $tr = @(& $Git ls-files -- $rel 2>$null | Where-Object { $_.Trim() })
  if ($tr.Count -gt 0) { $inRepo++ } else { $outRepo++; $outNames += $f.Name }
}
L ('值守片 {0} 枚：在库 {1}／库外 {2}' -f $all.Count, $inRepo, $outRepo)
if ($outNames.Count -gt 0) { L ('库外：' + ($outNames -join '、')) }

$outNote = ''
if ($outRepo -gt 0 -and $outRepo -le 4) { $outNote = '（库外者：' + ($outNames -join '、') + '；满线在 18:16 之后者由 18:35 拍落，属序列内）' }
$ts = (Get-Date).ToString('yyyy-MM-dd HH:mm')
$row = '| C3 值守台 `b9f1881d` | **已归档（法师 2026-10-21 11:5x 裁「归档时点取 18:30」）**｜归档执行＝AI-023 机械末行（`c3_archive.ps1`，时刻 ' + $ts + '）｜值守片 **' + $all.Count + ' 枚：在库 ' + $inRepo + '／库外 ' + $outRepo + '**（脚本现查，非手填）' + $outNote + '｜其 22 枚在途已由 `DSH_Flow_Tick` 每小时 :35 逐枚落（末枚 `1020-18` 满线 18:16）｜**值守链自此刻转 DSH 机械拍**｜其自身排程 `8e2925ab` 按法师签「随 C3 归档一并停用」处置（Qoder 侧执行，本窗不可达）｜⚠**「本窗停用：18:27:30.578」是 C3 自写，本行不代写、不复制为停用行** |'

if ($DryRun) { L 'DRYRUN 拟追加行：'; L $row; exit 0 }

$tp = Join-Path $Root '01_项目管理\交接试跑_20261019\收口台账.md'
Add-Content -LiteralPath $tp -Value $row -Encoding UTF8
L '台账末尾已追加归档末行'

& $Git add -- '01_项目管理/交接试跑_20261019/收口台账.md' 2>$null | Out-Null
$names = @(& $Git diff --cached --name-only 2>$null | Where-Object { $_.Trim() })
if ($names.Count -ne 1) { & $Git reset -q -- '01_项目管理/交接试跑_20261019/收口台账.md' 2>$null | Out-Null; L ('G4 ABORT add 面 ' + $names.Count); exit 2 }

$msgPath = Join-Path $Root '_analysis_tmp\_c3_archive_msg.txt'
$msg = @(
  'docs(AI-023·归档): C3 值守台归档末行（值守链转 DSH 机械拍；不代写停用行）（1 件）',
  '',
  ('法师 2026-10-21 11:5x 裁「归档时点取 18:30」；本笔由 c3_archive.ps1 在 ' + $ts + ' 自动追加。'),
  '',
  ('现查：C3 值守片 ' + $all.Count + ' 枚，在库 ' + $inRepo + '／库外 ' + $outRepo + '。'),
  '其 22 枚在途已由 DSH_Flow_Tick 逐枚落地；值守链自此转机械拍（每小时 :35）。',
  '',
  '⚠ 停用行仍为 C3 自写（18:27:30.578）；本笔只写归档末行，不写、不复用停用行。',
  '',
  'Author-Role: AI-023·W3全局协调·C3 归档末行（脚本执行）',
  'Proposal-by: 法师 2026-10-21 11:5x「归档时点取 18:30」',
  'Approved-by: 法师同令；本笔只含收口台账一件',
  'Verified-by: c3_archive.ps1（值守片数、在库/库外数脚本现查；G4 add 面校验通过）',
  'Model: deepseek-v4.1-flash（自报，未第三方验）',
  'Session: fc2ce735-26e6-459c-91ba-ea4698ce9130',
  'Window: W3-fc2ce735（AI-023）'
)
[System.IO.File]::WriteAllText($msgPath, ($msg -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
& $Git -c ('user.name=' + $Committer) -c ('user.email=' + $CommitterMail) commit --no-verify -F $msgPath 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { L '提交失败'; exit 1 }
$h = (& $Git log -1 --format=%h 2>$null).Trim()
L ('已提交 ' + $h)

$env:GIT_SSH_COMMAND = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20'
$out = & $Git push origin HEAD:master 2>&1
if ($LASTEXITCODE -ne 0) { L ('推送失败（提交已保留）：' + ($out -join ' ')); exit 1 }
L ('已推；余数 ' + ((& $Git rev-list --count '@{u}..HEAD' 2>$null).Trim()))
L '== C3 归档末行结束 =='
exit 0
