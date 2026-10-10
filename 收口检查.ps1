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

# ---------- 2. 决策登记（分片制口径） ----------
Section "2. Decision registration (shard mode, rule 2.7)"
$dline = Select-String -LiteralPath '01_项目管理\止观AI项目分工与决策日志.md' -Pattern '\*\*D(\d+)' |
         ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Sort-Object -Descending | Select-Object -First 1
$today = Get-Date -Format 'MMdd'
$shards = @(Get-ChildItem -LiteralPath '01_项目管理\登记分片' -Filter "D-$today-W*.md" -ErrorAction SilentlyContinue)
# 闸门自检（教训 7.1：本脚本自身判据亦须被核验）——2026-10-03 修：
# 旧写法 `-Filter "D-$today-W*x.md"` 里的 `x` 是**字面量**，W1a/W2b 这类真实命名**永不匹配**
# ⇒ 该闸连续两日恒报 0，且只出 NOTE 不出告警，谁也没发现。故补形状自检。
$shapeProbe = @(Get-ChildItem -LiteralPath '01_项目管理\登记分片' -Filter "D-*-W*.md" -ErrorAction SilentlyContinue)
if ($shapeProbe.Count -eq 0) {
    Bad "闸2 自检失败：登记分片目录中竟无 D-*-W*.md —— filter 形状可能有误，本闸可能恒为空转"
} else {
    Ok "闸2 自检：D 分片命名形状可匹配（历史 $($shapeProbe.Count) 件）"
}
Write-Host "legacy max D = D$dline (frozen tail only); today shards: $($shards.Count) [D-$today-Wxa style]" -ForegroundColor White
if ($shards.Count -eq 0) { Write-Host "[NOTE] no D-shard today - if this window carried a master decision, write one file per item into 登记分片\ (2.7); pure exec rounds skip" -ForegroundColor Gray }
else { Ok ("today D-shards registered: " + (($shards | ForEach-Object { $_.BaseName } | Sort-Object) -join ', ')) }

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

# ---------- 5. 提交信息 BOM 闸门（坑010-W / ZG-065 / D-0925-W3a） ----------
Section "5. 近 5 笔提交原始对象 subject 首三字节禁 BOM（EF BB BF）"
$bomHits = @()
# 注意：git 输出层会剥显 BOM（%s 读回首字符是干净的），只有原始提交对象里有 EF BB BF——
# 故必须 cat-file 读原始字节判首三字节，勿用 git log %s（那样闸门必哑火，教训7.1 实证于 ZG-065 建门时）。
$tmpf = Join-Path $env:TEMP 'bomchk.bin'
foreach ($h in (git log -5 --pretty=%H 2>$null)) {
    cmd /c "git cat-file commit $h > `"$tmpf`"" | Out-Null
    $raw = [System.IO.File]::ReadAllBytes($tmpf)
    $sep = -1; for ($i = 0; $i -lt $raw.Length - 1; $i++) { if ($raw[$i] -eq 0x0A -and $raw[$i+1] -eq 0x0A) { $sep = $i + 2; break } }
    if ($sep -ge 0 -and $raw.Length -ge $sep + 3 -and $raw[$sep] -eq 0xEF -and $raw[$sep+1] -eq 0xBB -and $raw[$sep+2] -eq 0xBF) {
        $bomHits += $h.Substring(0, 7)
    }
}
Remove-Item -LiteralPath $tmpf -ErrorAction SilentlyContinue
if ($bomHits.Count -gt 0) {
    foreach ($h in $bomHits) { Bad "subject 带 BOM（Set-Content/Out-File 坑）：$h —— 提交信息改走 bash heredoc 或 Write 工具（规约坑010-W）" }
} else { Ok "近 5 笔提交原始对象 subject 无 BOM。" }

# ---------- 6. 提交日期 vs Session 日期段（2026-10-01 法师立规；缘起 KZ-1001-W1a） ----------
# 规则：跨日会话每笔提交前重取系统日期，并以该日期定文件名前缀与 Session 日期段。
# 缘起：W1 窗 10-01 续做时沿用 0930，两笔提交文件名与 Session 均差一日（KZ-1001-W1a）。
Section "6. 提交日期 vs Session 日期段（跨日会话必重取日期）"
$headDate = (git log -1 --date=short --format=%ad 2>$null | Select-Object -First 1)
$headMsg = ((git log -1 --format=%B 2>$null) -join "`n")
$sesLine = ([regex]::Match($headMsg, '(?m)^Session:\s*(.+)$')).Groups[1].Value.Trim()
if (-not $sesLine) {
    Write-Host "[提示] 最新提交无 Session trailer，本门只对含 Session 的提交生效。"
} elseif ($sesLine -notmatch '(\d{8})') {
    Write-Host "[提示] Session 不含 8 位日期段（$sesLine），跳过日期比对。"
} else {
    $d8 = $Matches[1]
    $sesFmt = $d8.Substring(0, 4) + '-' + $d8.Substring(4, 2) + '-' + $d8.Substring(6, 2)
    if ($sesFmt -ne $headDate) {
        Bad "提交日 $headDate ≠ Session 日期段 $sesFmt（$sesLine）——跨日会话请重取系统日期（KZ-1001-W1a）"
    } else {
        Ok "提交日与 Session 日期段一致：$headDate"
    }
}
$addedFiles = @(git log -1 --diff-filter=A --name-only --format= 2>$null)
$badNames = @()
foreach ($f in $addedFiles) {
    if (-not $f) { continue }
    $m2 = [regex]::Match((Split-Path $f -Leaf), '^(20\d{6})')
    if ($m2.Success) {
        $dd = $m2.Groups[1].Value
        $ff = $dd.Substring(0, 4) + '-' + $dd.Substring(4, 2) + '-' + $dd.Substring(6, 2)
        if ($ff -ne $headDate) { $badNames += ("$dd  " + (Split-Path $f -Leaf)) }
    }
}
if ($badNames.Count -gt 0) {
    foreach ($n in $badNames) { Bad "新增文件名日期前缀与提交日不符：$n（历史不改写，请登记留证并改后续口径）" }
} else {
    Ok "上一笔新增文件的日期前缀与提交日一致（或无日期前缀）。"
}

# ---------- 8. 案例库索引一致性（2026-10-10 法师裁「要」；缘起：016～019 四卡入库时索引未回填，全靠手工回填、无闸可查） ----------
# 判据：某文体盘上卡片文件数 ＝ 索引表内行数。不等 ⇒ 要么有卡没登记（本闸要抓的），要么有行没卡（引用悬空）。
Section "8. 案例库索引一致性（盘上文件数 ＝ 索引表行数）"
$clRoot = Join-Path (Get-Location) '01_项目管理\案例库'
function ClRows($txt, $sectName) {
    $parts = [regex]::Split($txt, '(?m)^### ')
    foreach ($p in $parts) { if ($p.StartsWith($sectName)) { return @([regex]::Matches($p, '(?m)^\|\s*(\d{3})\s*\|')).Count } }
    return -1
}
$clSpecTxt = [System.IO.File]::ReadAllText((Join-Path $clRoot '00_案例库说明.md'), [System.Text.Encoding]::UTF8)
$clHotTxt = [System.IO.File]::ReadAllText((Join-Path $clRoot '判断实例\00_判断实例索引.md'), [System.Text.Encoding]::UTF8)
$clBad = 0
foreach ($c in @(
        @{ d = '决策判语'; n = ClRows $clSpecTxt '决策判语' },
        @{ d = '踩坑档案'; n = ClRows $clSpecTxt '踩坑档案' },
        @{ d = '复现路径'; n = ClRows $clSpecTxt '复现路径' },
        @{ d = '判断实例'; n = @([regex]::Matches($clHotTxt, '(?m)^\|\s*\*\*JP-(\d{3})\*\*\s*\|')).Count })) {
    $dir = Join-Path $clRoot $c.d
    if (-not (Test-Path -LiteralPath $dir)) { Bad "闸8：案例库子目录读不到 $c.d —— 目录被移动？本门不可信"; $clBad++; continue }
    $disk = @(Get-ChildItem -LiteralPath $dir -Filter '*.md' -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -notlike '00_*' -and $_.Name -notlike '99_*' -and $_.Name -notlike '*说明*' })
    # 闸门自检（教训 7.1）：索引里读到 0 行＝判据形状失效，绝不允许静默 PASS
    if ($c.n -lt 0) { Bad "闸8：$c.d 在索引中找不到对应小节标题——小节被改名？本门不可信"; $clBad++; continue }
    if ($c.n -eq 0) { Bad "闸8 自检失败：$c.d 索引行数为 0，而盘上有 $($disk.Count) 件——正则形状可能已失效，本门可能恒空转"; $clBad++; continue }
    if ($c.n -ne $disk.Count) {
        Bad "案例库索引与盘不符：$c.d 索引 $c.n 行 ≠ 盘上 $($disk.Count) 件 —— 差 $([Math]::Abs($c.n - $disk.Count))，请逐号对账后回填（016～019 那次漏登记即此类）"
        $clBad++
    }
}
if ($clBad -eq 0) { Ok "案例库四体索引行数与盘上卡片文件数一致（判断实例按热档行数计，依冷热分离）。" }

# ---------- 9. 架构台账 sourceRefs 空行探针（2026-10-10 法师裁「改为准」——仅此一项，本脚本其余一字不动） ----------
# ⚠本门只判「指向空行／越界」，**判不到「非空但错行」**（协调正本 §31.3：HEAD 侧那两行都有内容、只是指向了别的函数）。
#    不得把本门 PASS 当作锚点缺陷已了结。真判据「指向行内容与 ref 语义相符」仍候裁。
Section "9. sourceRefs 空行探针（HEAD 侧与工作区双侧复算）"
$amJson = Join-Path (Get-Location) '05_产品与开发\架构可视化\architecture-model.json'
if (-not (Test-Path -LiteralPath $amJson)) {
    Bad "闸9：读不到 architecture-model.json —— 台账被移动？本门不可信"
} else {
    $amTxt = [System.IO.File]::ReadAllText($amJson, [System.Text.Encoding]::UTF8)
    $refs = @([regex]::Matches($amTxt, '"([^"\r\n\\]*(?:[\\/][^"\r\n]*)?):(\d{1,6})"'))
    if ($refs.Count -eq 0) {
        Bad "闸9 自检失败：台账中一个 ``path:line'' 式 ref 都没读到——正则形状可能已失效，本门可能恒空转（教训 7.1／坑 017）"
    } else {
        $blobT = Join-Path $env:TEMP 'anchorblob.bin'
        $blankHits = @(); $oorHits = @(); $noHeadHits = 0
        foreach ($m in $refs) {
            $rp = ($m.Groups[1].Value -replace '\\', '/')
            $ln = [int]$m.Groups[2].Value
            & git cat-file -e "HEAD:$rp" 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) { $noHeadHits++; continue }   # 未入库新件（文件已在途），跳过 HEAD 侧判
            cmd /c "git cat-file blob HEAD:`"$rp`" > `"$blobT`"" 2>$null | Out-Null
            $raw = [System.IO.File]::ReadAllBytes($blobT)
            $lines = @([System.Text.Encoding]::UTF8.GetString($raw) -split "`n")
            if ($ln -lt 1 -or $ln -gt $lines.Count) { $oorHits += "$rp`:$ln"; continue }
            $cell = $lines[$ln - 1].Trim("`r", " ", "`t")
            if ($cell -eq '') { $blankHits += "$rp`:$ln" }
        }
        Remove-Item -LiteralPath $blobT -ErrorAction SilentlyContinue
        if ($blankHits.Count -gt 0) { foreach ($b in ($blankHits | Select-Object -Unique)) { Bad "sourceRefs 指向空行（HEAD 侧）：$b —— 该行在库中是空白，锚已失效，请按现势重出行号" } }
        if ($oorHits.Count -gt 0) { foreach ($o in ($oorHits | Select-Object -Unique)) { Bad "sourceRefs 行号越界（HEAD 侧）：$o" } }
        if ($blankHits.Count -eq 0 -and $oorHits.Count -eq 0) {
            Ok "sourceRefs 空行探针：复算 $($refs.Count) 个带行号 ref，零指空、零越界（其中 $noHeadHits 个所指文件尚未入库，跳过）。"
            Write-Host "     [提示] 本门判不到「非空但错行」，也判不到 HEAD 侧与工作区侧的语义差（正本 §31.3）。PASS ≠ 锚点已了结。" -ForegroundColor Gray
        }
    }
}

# ---------- 结论 ----------
Write-Host ""
if ($warn -gt 0) {
    Write-Host "结论：[收口未完] $warn 项告警。补齐后重跑本脚本；确属可豁免项（如纯执行轮无需 D 编号），在收口说明中写明理由。" -ForegroundColor Yellow
    exit 2
} else {
    Write-Host "结论：[收口要件齐] 可关窗/交付。" -ForegroundColor Green
    exit 0
}
