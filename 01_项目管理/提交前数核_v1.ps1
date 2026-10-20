# 提交前数核（PowerShell 版）· 替代跑不起来的 commit-msg 钩子
#
# 为什么有这个件：本机 `sh` 起不来（`couldn't create signal pipe, Win32 error 5`），`.git/hooks/commit-msg` 那个钩子
# **一次都没跑过**；而它要核的三项（件数／增删／六字段尾注）恰是复发最多的一族（坑 025／054／066）。
# 2026-10-20 本窗连栽两次：`01970f4` 写「单 33 行」实测 31；`273a892` 写「增 191」实测 110 —— **两次都是"手写数"**。
# ⇒ 判语 017：无检查点的规则不等于规则。本件就是这个检查点（只读、不改任何文件、不拦提交，退出码＝信号）。
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File 提交前数核_v1.ps1 -Message <提交信息文件>            # 对暂存区核
#   powershell -NoProfile -ExecutionPolicy Bypass -File 提交前数核_v1.ps1 -Message <文件> -Commit HEAD      # 对某笔核（留证／反证）
#
# 判据（与 commit-msg 钩子同口径，另加两项）：
#   ① 标题「N 件」 vs 实际件数              ② 标题/正文「增 X／删 Y」或「短统计＝N files changed, X insertions(+), Y deletions(-)」
#   ③ 六字段尾注 Author-Role/Proposal-by/Approved-by/Model/Session/Window   ④ 正文自称的「--numstat＝A ／ B」若出现，逐件比
# 退出码：0＝全过；1＝有 FAIL（含"无声明可核"）。

param(
  [Parameter(Mandatory = $true)][string]$Message,
  [string]$Commit = '',
  [string]$Root = 'D:\Project\zhiguanAI'
)
$ErrorActionPreference = 'Continue'
$fail = 0
function Say([string]$tag, [string]$msg) { Write-Host ("[{0}] {1}" -f $tag, $msg) }

$tool = Join-Path (Join-Path $Root '01_项目管理') '工具_git取数_沙箱兼容_v1.ps1'
if (-not (Test-Path $tool)) { Say 'FAIL' ("缺工具件：{0}" -f $tool); exit 1 }
. $tool
$probe = Test-GitUsable
if (-not $probe.Ok) { Say 'FAIL' ("git 不可执行 ⇒ 无法核数（{0}）" -f $probe.Detail); exit 1 }

if (-not (Test-Path $Message)) { Say 'FAIL' ("提交信息文件不在：{0}" -f $Message); exit 1 }
$msgText = [System.IO.File]::ReadAllText((Resolve-Path $Message).Path, [System.Text.Encoding]::UTF8)
$subject = ($msgText -split "`n")[0]

# ── 取实数 ────────────────────────────────────────────────
if ($Commit) {
  $scope = "commit $Commit"
  $names = (Invoke-Git ("show --name-only --format= {0}" -f $Commit)).Out
  $nums = (Invoke-Git ("show --numstat --format= {0}" -f $Commit)).Out
} else {
  $scope = '暂存区'
  $names = (Invoke-Git 'diff --cached --name-only').Out
  $nums = (Invoke-Git 'diff --cached --numstat').Out
}
$nameList = ($names -split "`n") | Where-Object { $_.Trim() -ne '' }
$realN = $nameList.Count
$add = 0; $del = 0
$perFile = @()
foreach ($l in ($nums -split "`n")) {
  if ($l.Trim() -eq '') { continue }
  $p = $l -split "`t"
  if ($p.Count -ge 2 -and $p[0] -match '^\d+$') { $add += [int]$p[0]; $del += [int]$p[1]; $perFile += [pscustomobject]@{ Add = [int]$p[0]; Del = [int]$p[1]; Path = $p[2] } }
}
Say 'GATE' ("== 提交前数核（{0}）==" -f $scope)
Say 'OK' ("实际：{0} 件｜增 {1}／删 {2}" -f $realN, $add, $del)

# ── ① 件数 ────────────────────────────────────────────────
$claimN = $null
if ($subject -match '([0-9]+)\s*件') { $claimN = [int]$Matches[1] }
if ($claimN -ne $null) {
  if ($claimN -eq $realN) { Say 'OK' ("① 件数：标题称 {0} 件，实际 {1} 件" -f $claimN, $realN) }
  else { Say 'FAIL' ("① 件数：标题称 {0} 件，实际 {1} 件" -f $claimN, $realN); $fail++ }
} else { Say 'WARN' '① 件数：标题未自称件数 ⇒ 无可核（不判绿）' }

# ── ② 增删：三种写法都认 ──────────────────────────────────
# ⚠ v1.0 缺陷（当轮自创自纠）：原正则不锚行首 ⇒ **正文里引用旧笔的「短统计＝…」也会被抓**
#    （本窗 msg11 引用 273a892 的 191，被误判成自己的声明，fail=1）。改锚行首 `(?m)^短统计`。
#    留此注防复发：**引用 ≠ 声明**，检查器必须能分开这两件事。
$claims = @()
$mShort = [regex]::Match($msgText, '(?m)^短统计[＝=]\s*([0-9]+)\s*files changed,\s*([0-9]+)\s*insertions?\(\+\)(?:,\s*([0-9]+)\s*deletions?\(-\))?')
if ($mShort.Success) {
  $dC = 0
  if ($mShort.Groups[3].Success) { $dC = [int]$mShort.Groups[3].Value }
  $claims += [pscustomobject]@{ Kind = '短统计'; Add = [int]$mShort.Groups[2].Value; Del = $dC }
}
if ($subject -match '增\s*([0-9,]+)／删\s*([0-9,]+)') {
  $claims += [pscustomobject]@{ Kind = '标题'; Add = [int]($Matches[1] -replace ',', ''); Del = [int]($Matches[2] -replace ',', '') }
}
# ⚠ v1.1 补（2026-10-20 16:3x，第四处同族）：**自称却为空**也要抓。
#    实证：a72734c 标题写成「（1 件；增 ／删 ）」——数字没进模板，而 v1.0 只核"能解析的数"，
#    对这种空壳只报 WARN「未自称」，等于放过。⇒ 加一条：出现「增 ／删」形状但取不到数字 ⇒ FAIL。
# 又栽一次同一个坑（引用≠声明）：v1.1 初版扫全文，把我**引用**旧笔空壳的那句也当成本笔自称 ⇒ 改**只扫标题行**。
if ($subject -match '增\s*／\s*删') { Say 'FAIL' '② 增删：标题自称却为空（「增 ／删」未带数字）⇒ 按未核处理'; $fail++ }
if ($claims.Count -eq 0) { Say 'WARN' '② 增删：未自称增删数 ⇒ 无可核' }
foreach ($c in $claims) {
  if ($c.Add -eq $add -and $c.Del -eq $del) { Say 'OK' ("② 增删（{0}）：称 增 {1}／删 {2}，实际同值" -f $c.Kind, $c.Add, $c.Del) }
  else { Say 'FAIL' ("② 增删（{0}）：称 增 {1}／删 {2}，实际 增 {3}／删 {4}" -f $c.Kind, $c.Add, $c.Del, $add, $del); $fail++ }
}

# ── ③ 六字段尾注 ──────────────────────────────────────────
$missing = @()
foreach ($k in @('Author-Role', 'Proposal-by', 'Approved-by', 'Model', 'Session', 'Window')) {
  if ($msgText -notmatch ("(?m)^" + $k + ":")) { $missing += $k }
}
if ($missing.Count -eq 0) { Say 'OK' '③ 六字段尾注齐' } else { Say 'FAIL' ("③ 缺尾注：{0}" -f ($missing -join '／')); $fail++ }

# ── ④ 正文若逐件列了 numstat，逐件比 ──────────────────────
$listed = [regex]::Matches($msgText, '(?m)^([0-9]+)\s*／\s*([0-9]+)\s*／\s*(\S.*)$')
if ($listed.Count -gt 0) {
  $bad = 0
  foreach ($m in $listed) {
    $a = [int]$m.Groups[1].Value; $d = [int]$m.Groups[2].Value; $p = $m.Groups[3].Value.Trim()
    $hit = $perFile | Where-Object { $p -like ('*' + $_.Path) -or $_.Path -like ('*' + $p) } | Select-Object -First 1
    if ($hit -and ($hit.Add -ne $a -or $hit.Del -ne $d)) { Say 'FAIL' ("④ 逐件：{0} 称 {1}／{2}，实际 {3}／{4}" -f $hit.Path, $a, $d, $hit.Add, $hit.Del); $bad++ }
  }
  if ($bad -eq 0) { Say 'OK' ("④ 逐件 numstat {0} 行与实数一致" -f $listed.Count) } else { $fail += $bad }
} else { Say 'WARN' '④ 逐件 numstat：正文未列 ⇒ 无可核' }

Say 'END' ("fail={0}" -f $fail)
exit ([int]($fail -gt 0))
