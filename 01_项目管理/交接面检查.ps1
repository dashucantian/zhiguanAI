# 交接面检查（只读）· 开工五问 ＋ 收口五件
# 来源：法师 2026-10-20 准"升两条"之第二条（收口五件落成检查点）；第一条为《AI-开工入口.md》§一.1 加"交接单"条件必读。
# 为什么单独立件、不并进 收口检查.ps1（516 行、四窗共用）：主脚本 10-08 法师裁"不准修"、10-14 才准过修字；新门独立，风险隔离，主脚本一行未改。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File 交接面检查.ps1 -Root D:\Project\zhiguanAI [-Handover "01_项目管理\...\交接单_v1.md"]
# 只读，不改任何文件。退出码 0＝全过；1＝有 FAIL（仅信号，不拦提交；拦阻权在法师）。
#
# ── 2026-10-20 补正（DSH 承接窗 fc2ce735）────────────────────────────────
# 原版在本机**跑不起来**，两处硬伤，均已实测：
#   ① **编码**：原文件为 UTF-8 无 BOM。Windows PowerShell 5.1 按 GBK 解析，中文串整段乱码 ⇒ ParserError、退码 1
#      （本机无 pwsh，只有 5.1；`pwsh -File` 那行用法在本机不可执行）。补法＝改存 UTF-8 **带 BOM**
#      （与 `收口检查.ps1` 第 7 门对 `.ps1` 的豁免口径一致：`.ps1` 除外）。
#   ② **git 假绿**：原版三处裸调 `git`，本机沙箱下一律 `Access is denied`；捕获失败返回空 ⇒ 打印"committer 仍是默认/空"的
#      **WARN**、并**静默跳过**工作树检查——看起来跑过了，其实两项都没核（坑 053「一致性闸门仍可为假绿」同族）。
#      补法＝引 `工具_git取数_沙箱兼容_v1.ps1`（cmd 内重定向＋完成哨兵），并加一条**探针**：git 不可用即 FAIL，不再降级成 WARN。
# 反证（判据自身也要被验，规约 §五.8）：
#   ① `-GitExe`→不存在路径：必出 FAIL 且退码 1；② 正常路径：出 OK 行、无 FAIL；③ 两跑记录见分片 `D-1020-W3COORD-fc2ce735.md`。

param(
  [string]$Root = 'D:\Project\zhiguanAI',
  [string]$Handover = ''
)
$ErrorActionPreference = 'Continue'
$fail = 0
function Say([string]$tag, [string]$msg) { Write-Host ("[{0}] {1}" -f $tag, $msg) }

Say 'GATE' '== 开工五问 =='
$st = Join-Path $Root '00_当前状态.md'
$en = Join-Path $Root 'AI-开工入口.md'
if (Test-Path $st) { Say 'OK' ("必读1 00_当前状态.md 在（mtime {0}）" -f (Get-Item $st).LastWriteTime.ToString('MM-dd HH:mm:ss')) }
else { Say 'FAIL' '必读1 00_当前状态.md 不存在'; $fail++ }
if (Test-Path $en) { Say 'OK' ("必读2 AI-开工入口.md 在（{0} 行）" -f (Get-Content $en -Encoding utf8).Count) }
else { Say 'FAIL' '必读2 AI-开工入口.md 不存在'; $fail++ }

# ── git 取数（沙箱兼容）· 探针先行 ────────────────────────────────
$tool = Join-Path (Join-Path $Root '01_项目管理') '工具_git取数_沙箱兼容_v1.ps1'
$gitOk = $false; $gitVer = ''; $gitWhy = ''
if (Test-Path $tool) {
  . $tool
  $probe = Test-GitUsable
  $gitOk = $probe.Ok; $gitVer = $probe.Version; $gitWhy = $probe.Detail
  if ($gitOk) { Say 'OK' ("git 探针通：{0}" -f $gitVer) }
  else { Say 'FAIL' ("git 不可执行 ⇒ 下面两项 git 面**未核**，不得报绿（{0}）" -f $gitWhy); $fail++ }
} else {
  Say 'FAIL' ("缺工具件：{0} ⇒ git 面未核，不得报绿" -f $tool); $fail++
}

if ($Handover) {
  $h = Join-Path $Root $Handover
  if (Test-Path $h) { Say 'OK' ("必读3 交接单在：{0}（{1} B）" -f $Handover, (Get-Item $h).Length) }
  else { Say 'FAIL' ("必读3 交接单不存在：{0}" -f $Handover); $fail++ }
  if ($gitOk) {
    $who = (Invoke-Git 'config --get user.name').Out.Trim()
    if ($who -and $who -ne 'zhiguanAI-agent') { Say 'OK' ("committer 已显式指定：{0}" -f $who) }
    else { Say 'WARN' ("committer 仍是默认/空：{0} => 按 §〇 第 3 项须 -c user.name='<窗号>'" -f $who) }
  } else { Say 'WARN' 'committer 面未核（git 不可执行；非"未设置"，勿按未设置处理）' }
} else {
  Say 'WARN' '未给 -Handover：按"无在途交接"处理；§一.1 条件必读据此豁免，收口轮须复核此假设'
}

if ($gitOk) {
  $dirty = (Invoke-Git 'status --porcelain').Out
  $dirtyN = 0
  if ($dirty) { $dirtyN = (($dirty -split "`n") | Where-Object { $_.Trim() -ne '' }).Count }
  if ($dirtyN -gt 0) { Say 'WARN' ("工作树有 {0} 行未提交（含他窗在途）=> 按 §〇 闸门：先分清归属再动手，不覆盖不叠加" -f $dirtyN) }
  else { Say 'OK' '工作树干净（git status --porcelain 空串）' }
} else { Say 'WARN' '工作树面未核（git 不可执行；不等于干净）' }

Say 'GATE' '== 收口五件 =='
if ($Handover -and (Test-Path (Join-Path $Root $Handover))) {
  $h = Join-Path $Root $Handover
  $anchor = "$h.sha256"
  if (Test-Path $anchor) { Say 'OK' ("1 单在盘（锚 {0} 在）" -f (Split-Path $anchor -Leaf)) } else { Say 'FAIL' '1 单无 .sha256 锚'; $fail++ }
  $txt = [System.IO.File]::ReadAllText($h, [System.Text.Encoding]::UTF8)
  $lines = ([regex]::Matches($txt, "`n")).Count
  if ($lines -le 70) { Say 'OK' ("页尺 成单 {0} 行 <=70" -f $lines) } else { Say 'WARN' ("页尺 成单 {0} 行 >70（记'填不下'，灯号黄）" -f $lines) }
  if ($txt -match '复述') { Say 'OK' '2 复述已落' } else { Say 'FAIL' '2 未见复述痕迹'; $fail++ }
  if ($txt -match '查库' -and $txt -match '查盘' -and $txt -match '查信' -and $txt -match '搜裁') { Say 'OK' '3 四查已落' } else { Say 'FAIL' '3 四查不全'; $fail++ }
  if ($txt -match '回执落点') { Say 'OK' '4 回执落点已写死' } else { Say 'FAIL' '4 单⑩ 未写回执落点'; $fail++ }
  $receipt = Get-ChildItem (Split-Path $h -Parent) -File -Filter '*接管回执*' -ErrorAction SilentlyContinue
  if ($receipt) { Say 'OK' ("5 回执已落：{0}" -f $receipt[0].Name) } else { Say 'FAIL' '5 盒内无接管回执'; $fail++ }
  if ($txt -match '本窗停用') { Say 'OK' '关窗行在' } else { Say 'WARN' '关窗行未落（不得报已停用）' }

  # ── 归档三查（法师 2026-10-21 01:1x 准 P-A；口径＝收口台账「关窗口径」三样齐：①盘上件已入库 ②回执有补签 ③未验面已转出且回执末行有停用行）──
  # 只报不拦（不进 $fail）：归档面另有收口台账闸，本处只把"齐没齐"点亮。
  Say 'GATE' '== 归档三查（只报不拦）=='
  $arc = 0
  $rel = $Handover -replace '\\', '/'
  if ($gitOk) {
    $q = Invoke-Git ('ls-files --error-unmatch "' + $rel + '"')
    if ($q.Rc -eq '0') { Say 'OK' '归档① 盘上件已入库'; $arc++ } else { Say 'WARN' '归档① 盘上件未入库（ls-files 退非 0）——归档三样不齐' }
  } else { Say 'WARN' '归档① 未核（git 不可执行）' }
  $rcpts = @(Get-ChildItem (Split-Path $h -Parent) -File -Filter '*回执*.md' -ErrorAction SilentlyContinue)
  $sign = $false; $stop = $false
  foreach ($f in $rcpts) {
    $rt = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
    if ($rt -match '补签') { $sign = $true }
    if ($rt -match '本窗停用：') { $stop = $true }
  }
  if ($sign) { Say 'OK' '归档② 回执有补签痕迹'; $arc++ } else { Say 'WARN' ("归档② 盒内 {0} 份回执均无补签痕迹" -f $rcpts.Count) }
  if ($stop) { Say 'OK' '归档③ 回执末有停用行（本窗停用：）'; $arc++ } else { Say 'WARN' '归档③ 未见到「本窗停用：」行——不得报已停用' }
  Say 'INFO' ("归档三查 {0}/3 齐（本项不拦提交，不判灯号）" -f $arc)
} else {
  Say 'WARN' '未给 -Handover：收口五件无法核（不判绿）'
}

Say 'END' ("fail={0}" -f $fail)
exit ([int]($fail -gt 0))
