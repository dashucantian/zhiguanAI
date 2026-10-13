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
    if ($c.n -lt 0) { Bad "闸8：$($c.d) 在索引中找不到对应小节标题——小节被改名？本门不可信"; $clBad++; continue }
    if ($c.n -eq 0) { Bad "闸8 自检失败：$($c.d) 索引行数为 0，而盘上有 $($disk.Count) 件——正则形状可能已失效，本门可能恒空转"; $clBad++; continue }
    if ($c.n -ne $disk.Count) {
        Bad "案例库索引与盘不符：$($c.d) 索引 $($c.n) 行 ≠ 盘上 $($disk.Count) 件 —— 差 $([Math]::Abs($c.n - $disk.Count))，请逐号对账后回填（016～019 那次漏登记即此类）"
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

# ---------- 10. 本轮案例库提取声明（2026-10-11 法师裁「那就根据现在的实际情况调整为必做 收口检查」） ----------
# 背景：法师 2026-10-10 已把"每天从各窗进程提取有价值经验落案例库"授为 W3 常设职责，但**无检查点**
#   ⇒ 判语 017 的核心结论正是「无检查点的规则不等于规则」。本门就是给它补的检查点。
# 判据（机器能判的那一半）：机器判不了"这轮有没有值得留档的经验"（语义判断），
#   但判得了"今天有动静的窗有没有明确表态"。故判据＝**表态制**：
#   今日己档（`信箱\engine\巡检日志-*.txt`，mtime＝今日）里必须有一行当日声明，形状固定：
#     案例库提取｜YYYY-MM-DD｜已提取 N 张（编号…）      或
#     案例库提取｜YYYY-MM-DD｜无可提取（理由一句话）
#   不表态＝告警 ⇒ 把"没人想起来"变成可见信号，而不是靠人记性。
# ⚠自检（教训 7.1／坑 017：判据形状失效绝不允许静默 PASS）：
#   今日有窗动工、而**全区一份声明都读不到** ⇒ 报「制度未落地」并只报制度状态、不逐窗点名
#   （新制首日逐窗点名＝把闸门建成噪音；坑 021 同族：恒红的警报会训练人不看警报）。
Section "10. 本轮案例库提取声明（今日有动静的窗须在自己己档表态）"
$engDir = Join-Path (Get-Location) '01_项目管理\信箱\engine'
$todayStr = (Get-Date).ToString('yyyy-MM-dd')
$clMark = "案例库提取｜$todayStr"
if (-not (Test-Path -LiteralPath $engDir)) {
    Bad "闸10：读不到信箱 engine 区 —— 目录被移动？本门不可信"
} else {
    $todayLogs = @(Get-ChildItem -LiteralPath $engDir -Filter '巡检日志-*.txt' -ErrorAction SilentlyContinue |
                   Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date } |
                   Where-Object { $_.Name -notmatch '^巡检日志-C3-' })  # 按活跃窗对齐（法师 10-14 裁 P14）：C3 值守窗系自动执行，不要求案例库提取声明
    if ($todayLogs.Count -eq 0) {
        Write-Host "[NOTE] 今日无窗己档有动静（mtime 判据）——本门前提不成立，不判 PASS 也不判告警。" -ForegroundColor Gray
    } else {
        $declared = @(); $silent = @()
        foreach ($lg in $todayLogs) {
            $txt = [System.IO.File]::ReadAllText($lg.FullName, [System.Text.Encoding]::UTF8)
            if ($txt.Contains($clMark)) { $declared += $lg.Name } else { $silent += $lg.Name }
        }
        if ($declared.Count -eq 0) {
            Bad "闸10 制度未落地：今日 $($todayLogs.Count) 个窗有动静，全区**零份**当日声明（找的是字面「$clMark」）。首上线只报制度状态、不逐窗点名；规约 §二.12 已定形状，各窗下一轮收口补一行即可。"
        } else {
            if ($silent.Count -eq 0) {
                Ok "今日有动静的 $($todayLogs.Count) 个窗全部留下当日案例库提取声明（$($declared -join '、')）。"
            } else {
                Bad "案例库提取声明缺 $($silent.Count) 窗：$($silent -join '、') —— 已表态者：$($declared -join '、')。缺者在自己己档补一行（形状见规约 §二.12），历史轮不回改。"
            }
        }
    }
}

# ---------- 11. 件数口径探针（2026-10-13 法师裁「准修」第二处窄例外：只加本门，其余一字不动） ----------
# 病根（10-12 一天内两窗同型）：报"在途 N 件"没声明按哪一侧数 ⇒ 协调窗 21:10 函写"您 11 件在途"，
#   按 git 可见面实为 2 件（其余 9 件在 ignore 区）；人机建构窗 15:4x 那份"候放行清单"同源失真。
#   判语 017 同族：写在文书里的口径不等于生效，须挂检查点。§二.15 第①款的落地面。
# 判据形状：凡"在途 N 件／N 件在途／候放行 N 件"一类汇总，**同一行必须带口径词**
#   （盘上／git 可见／git可见／tracked／未跟踪／已跟踪／暂存）；缺即点名 文件:行号。
# 检索面：今日（本地日期）mtime 改动过的 己档 与 信箱函件（只读，不判历史轮，历史不回改）。
Section "11. 件数口径探针（报『在途 N 件』须声明按哪一侧数·法师 10-13 准修）"
$engDir11 = Join-Path (Get-Location) '01_项目管理\信箱\engine'
if (-not (Test-Path -LiteralPath $engDir11)) {
    Bad "闸11：读不到信箱 engine 区 —— 目录被移动？本门不可信"
} else {
    $scope11 = @(Get-ChildItem -LiteralPath $engDir11 -Filter '*.txt' -ErrorAction SilentlyContinue |
                 Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date })
    $scope11 += @(Get-ChildItem -LiteralPath $engDir11 -Filter '*.md' -ErrorAction SilentlyContinue |
                  Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date })
    if ($scope11.Count -eq 0) {
        Write-Host "[NOTE] 闸11：今日无己档／信件有动静（mtime 判据）——本门前提不成立，不判 PASS 也不判告警。" -ForegroundColor Gray
    } else {
        $re11  = '(在途\s*[0-9]+\s*件|[0-9]+\s*件在途|候放行[^，。]{0,8}[0-9]+\s*件)'
        $ok11  = '(盘上|git 可见|git可见|tracked|未跟踪|已跟踪|暂存)'
        $today11 = (Get-Date).ToString('yyyy-MM-dd')
        $n11 = 0; $miss11 = @(); $skipped11 = 0
        foreach ($f in $scope11) {
            $lines11 = [System.IO.File]::ReadAllLines($f.FullName, [System.Text.Encoding]::UTF8)
            # 扫描面＝自今日首轮头行「【yyyy-MM-dd」起（己档惯例）。历史轮不回改，故不判历史行；
            #   找不到今日头行 ⇒ 整档扫（保守，不放过"改了却没记轮次"的情形）。信箱函件为一次性文书，整件扫。
            $start11 = 0
            if ($f.Extension -eq '.txt') {
                $found11 = -1
                for ($j = 0; $j -lt $lines11.Count; $j++) {
                    if ($lines11[$j].StartsWith('【' + $today11)) { $found11 = $j; break }
                }
                if ($found11 -ge 0) { $start11 = $found11; $skipped11 += $found11 }
            }
            for ($i = $start11; $i -lt $lines11.Count; $i++) {
                # 逐行二次过滤（10-13 01:1x，VR 窗 `73336324` 01:09 复函指出后补）：
                #   行首带日期者（「2026-10-01 …」或「【2026-10-13 …】」），日期非今日 ⇒ 跳过并计数。
                #   病灶＝`巡检日志-W1.txt:16/17/18` 三行是 **10-01 的旧文**，因有人今日往同一份旧档追加一行
                #   把**文件 mtime 顶成今日**，于是整档历史被拉进"今日"检索面——mtime 判据看不出这一层。
                if ($f.Extension -eq '.txt' -and $lines11[$i] -match '^\s*【?(\d{4}-\d{2}-\d{2})') {
                    if ($Matches[1] -ne $today11) { $skipped11++; continue }
                }
                if ($lines11[$i] -match $re11) {
                    $n11++
                    if ($lines11[$i] -notmatch $ok11) {
                        $miss11 += ('{0}:{1}' -f $f.Name, ($i + 1))
                    }
                }
            }
        }
        if ($miss11.Count -eq 0) {
            Ok "闸11：今日 $($scope11.Count) 份动静文书里 $n11 处『在途／候放行 N 件』全部带口径字样（盘上／git 可见／tracked／暂存）；己档自今日首轮头行起扫，已跳过历史行 $skipped11 行。"
        } else {
            $show11 = ($miss11 | Select-Object -First 8) -join '、'
            Bad "闸11：$n11 处件数表述中有 $($miss11.Count) 处未声明口径（§二.15）：$show11$(if ($miss11.Count -gt 8) { ' …余' + ($miss11.Count - 8) + '处' }) —— 就地补『盘上』或『git 可见』即可；历史轮不回改（己档已跳过历史行 $skipped11 行）。"
        }
    }
}

# ---------- 12/13/14. 开局对账与呈面纪律三闸门（2026-10-13 法师裁「P25 收窄后的四条已落，要真闸门」） ----------
# 依据＝§二.16 四款中的可机判三款；第四款（换窗判据＝上下文体量＋任务线收口两条同成立）**属语义判断，本脚本不假称已闸**，见文末 [NOTE]。
# 病根（10-13 实测）：①待裁单 12 行超上限却无出口动作，把候裁项挤回正文漂了 3 轮（坑 043）；
#   ②本窗一天内两犯"空结果当不存在"（坑 044 甲乙丙），其中丙型＝拿**条目标题**判**条文存在性**，
#     差点在规约里造出两对重复条文。判语 017 同族：写在规约里的纪律不等于生效，须挂检查点。
Section "12. 协调窗本轮是否留了『待裁单对账』行（§二.16 第②款）"
$engDir12 = Join-Path (Get-Location) '01_项目管理\信箱\engine'
$today12 = (Get-Date).ToString('yyyy-MM-dd')
$coord12 = @(Get-ChildItem -LiteralPath $engDir12 -Filter '巡检日志-W3-*.txt' -ErrorAction SilentlyContinue |
             Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date })
# 生效时点＝规约正本 mtime（§二.16 落文那一刻）；早于它的不判（新制不溯及既往，坑 021／坑 041 同源）
$cut12 = if (Test-Path -LiteralPath 'AI-开工入口.md') { (Get-Item -LiteralPath 'AI-开工入口.md').LastWriteTime } else { (Get-Date).Date }
$coord12 = @($coord12 | Where-Object { $_.LastWriteTime -gt $cut12 })
if ($coord12.Count -eq 0) {
    Write-Host "[NOTE] 闸12：规约 §二.16 落文（$($cut12.ToString('HH:mm:ss'))）之后无协调窗己档动静——本门今日无可判对象。" -ForegroundColor Gray
} else {
    $silent12 = @()
    foreach ($f in $coord12) {
        $ls12 = [System.IO.File]::ReadAllLines($f.FullName, [System.Text.Encoding]::UTF8)
        $st12 = 0
        for ($j = 0; $j -lt $ls12.Count; $j++) { if ($ls12[$j].StartsWith('【' + $today12)) { $st12 = $j; break } }
        $hit12 = $false
        for ($i = $st12; $i -lt $ls12.Count; $i++) { if ($ls12[$i].Contains('待裁单对账')) { $hit12 = $true; break } }
        if (-not $hit12) { $silent12 += $f.Name }
    }
    if ($silent12.Count -eq 0) { Ok "闸12：今日 $($coord12.Count) 份协调窗己档均留「待裁单对账」行（现势行数／新增落单／漂在正文三项齐）。" }
    else { Bad "闸12：有动静却未留对账行（§二.16②）：$($silent12 -join '、') —— 每轮收尾固定一行「待裁单对账：现势 N 行｜本轮新增落单 X 条｜漂在正文 Y 条」，Y>0 当轮补。" }
}

Section "13. 待裁单超上限是否走了上报出口（§二.16 第③款·防"少写一行自行消数"）"
$dj13 = Join-Path (Get-Location) '01_项目管理\待裁单.md'
if (-not (Test-Path -LiteralPath $dj13)) {
    Bad "闸13：读不到 待裁单.md —— 目录被移动？本门不可信"
} else {
    $ls13 = [System.IO.File]::ReadAllLines($dj13, [System.Text.Encoding]::UTF8)
    $rows13 = @($ls13 | Where-Object { $_ -match '^\| \*\*P[0-9]+\*\*' })
    $head13 = ($ls13 | Select-Object -First 6) -join "`n"
    if ($rows13.Count -le 8) {
        Ok "闸13：待裁单活行 $($rows13.Count) 行 ≤ 上限 8，无需上报出口。"
    } else {
        if ($head13 -match '示删并|放宽到') {
            Ok "闸13：待裁单活行 $($rows13.Count) 行＝超上限 $($rows13.Count - 8) 行，头部已照直上报「请您示删并或放宽」并附可合并项（§二.16③ 合规；本门不判"该不该超"，只判"有没有瞒着您消数"）。"
        } else {
            Bad "闸13：待裁单活行 $($rows13.Count) 行已超上限 8，但**头部六行内无「请您示删并或放宽／放宽到」上报字样** —— 正是 §二.16③ 禁止的形状：不得用"少写一行"自行消数，须照直上报并附可合并清单。"
        }
    }
}

Section "14. 否定断言须带取法标记（§二.16 第①款·坑 044 甲乙两型＝数值零计数型）"
$scope14 = @(Get-ChildItem -LiteralPath $engDir12 -Filter '*.txt' -ErrorAction SilentlyContinue |
             Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date })
$scope14 += @(Get-ChildItem -LiteralPath $engDir12 -Filter '*.md' -ErrorAction SilentlyContinue |
              Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date })
# 生效时点＝§二.16 入库那一次提交的作者时刻（`git log --reverse -S` 现取，--reverse 钉住最早一条 ⇒ 历史事实，不随后续加注漂移）。
# ⛔旧写法＝取 AI-开工入口.md 的 mtime：任何窗在规约里加一行注记就把时点推后 ⇒ 本门检查面静默缩小，
#   且缩小后报 NOTE 不报 FAIL（10-13 实证：改一次规约，8 处零计数告警当场消失＝坑 030「门14 致盲」形；法师 10-14 裁「三条都做」＝本行准修字）。
$guige14 = Join-Path (Get-Location) 'AI-开工入口.md'
$raw14 = ''
if (Test-Path -LiteralPath $guige14) {
    $raw14 = (@(git log --reverse --format='%ct|%h' -S'开局对账与呈面纪律' -- 'AI-开工入口.md' 2>$null) | Select-Object -First 1)
}
$cutoff14 = (Get-Date).Date; $anchor14 = '回退＝今日零点（取不到 §二.16 入库提交）'
if ($raw14 -and $raw14 -match '^(\d+)\|(\w+)') {
    $cutoff14 = [datetimeoffset]::FromUnixTimeSeconds([long]$Matches[1]).LocalDateTime
    $anchor14 = '§二.16 入库提交 ' + $Matches[2] + '＝' + $cutoff14.ToString('MM-dd HH:mm:ss') + '（git --reverse -S 现取）'
}
$scope14 = @($scope14 | Where-Object { $_.LastWriteTime -gt $cutoff14 })
if ($scope14.Count -eq 0) {
    Write-Host "[NOTE] 闸14：无生效时点（$anchor14）之后的动静文书——本门今日无可判对象。" -ForegroundColor Gray
} else {
    # 断言侧**只收数值零计数型**（这类会直接导出"那就别做了"的动作，危害最实；坑 044 甲＝grep 判据抓空、乙＝netstat 空输出）
    #  ⛔不收「不存在／从未／盘上无／无成文」等叙述型：实测其中多数命中行是**引用别人（含自己）旧错**的元叙述，判它必误报（10-13 首跑 11 处误报 4 处）。
    $re14 = '(零命中|0 命中|命中 ?0|＝ ?0 ?(个|处|行|件|笔)|全库 ?0|返回空|输出为空)'
    # 证据侧按首跑误报补词：mtime／实点／实查／实跑／现跑／逐行 均为本仓通行取法标记
    $ok14 = '(检索面|排除面|判据|grep|awk|sed|python|命令|测于|实测|实点|实查|实跑|现跑|现量|复算|口径|mtime|〔测|〔1[0-9]:| wc |ls )'
    $n14 = 0; $miss14 = @()
    foreach ($f in $scope14) {
        $ls14 = [System.IO.File]::ReadAllLines($f.FullName, [System.Text.Encoding]::UTF8)
        $st14 = 0
        if ($f.Extension -eq '.txt') {
            $fd14 = -1
            for ($j = 0; $j -lt $ls14.Count; $j++) { if ($ls14[$j].StartsWith('【' + $today12)) { $fd14 = $j; break } }
            if ($fd14 -ge 0) { $st14 = $fd14 }
        }
        for ($i = $st14; $i -lt $ls14.Count; $i++) {
            if ($ls14[$i] -match $re14) {
                $n14++
                if ($ls14[$i] -notmatch $ok14) { $miss14 += ('{0}:{1}' -f $f.Name, ($i + 1)) }
            }
        }
    }
    if ($n14 -eq 0) { Ok "闸14：生效时点后动静文书 $($scope14.Count) 份内未出现数值零计数型断言，无可判对象。" }
    elseif ($miss14.Count -eq 0) { Ok "闸14：$($scope14.Count) 份文书里 $n14 处零计数断言全部自带取法标记（检索面／mtime／实点／复算…），未犯坑 044。" }
    else {
        $show14 = ($miss14 | Select-Object -First 8) -join '、'
        Bad "闸14：$n14 处零计数断言中有 $($miss14.Count) 处未带取法标记（§二.16①／坑 044）：$show14$(if ($miss14.Count -gt 8) { ' …余 ' + ($miss14.Count - 8) + ' 处' }) —— 报"没有"前先做正向自检：拿一个已知存在的同类样本用同一判据抓，抓不到＝判据坏，不是东西不存在。"
    }
}

# ---------- 判据自检：闸门自己有没有被改盲（法师 10-14 裁「三条都做」之第三条） ----------
# 触发条件＝本脚本的 mtime 晚于基线文件（＝"改过闸门，且改后还没重新记过盲区"）。平时只两个 stat，零成本。
# 为什么这样触发：诱饵集 0.18 秒、判据从本文件现读——只在"判据动过"之后跑，正好覆盖回归风险，不必每次提交都跑。
$canary15 = Join-Path (Get-Location) '01_项目管理\语料工程\闸门诱饵集\canary.py'
$base15 = Join-Path (Get-Location) '01_项目管理\语料工程\闸门诱饵集\已知盲区.json'
$gateSelf = if ($PSCommandPath) { $PSCommandPath } else { Join-Path (Get-Location) '收口检查.ps1' }
if ((Test-Path -LiteralPath $canary15) -and (Test-Path -LiteralPath $base15) -and (Test-Path -LiteralPath $gateSelf) -and
    ((Get-Item -LiteralPath $gateSelf).LastWriteTime -gt (Get-Item -LiteralPath $base15).LastWriteTime)) {
    $env:PYTHONIOENCODING = 'utf-8'
    $out15 = ''
    try { $out15 = (@(& python $canary15 --ids 2>$null) -join '') } catch { $out15 = '' }
    if ("$out15".Trim() -eq '') {
        Bad "诱饵集没跑起来（python 调不到／脚本改名／抠不到判据）⇒ 本自检静默失效，按未过处理，不许当绿灯。"
    } else {
        $now15 = @("$out15".Trim() -split ',' | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
        # ⚠必须显式 -Encoding UTF8：基线是无 BOM 的 UTF-8，Windows PowerShell 5.1 缺省按 GBK 解⇒
        #   多字节被两两吞掉、反斜杠消失 ⇒ ConvertFrom-Json 报"无效"⇒ 基线读成 0 条＝假称"全是新盲区"。（同族＝门4 编码坑）
        $known15 = @()
        try {
            $known15 = @(((Get-Content -Raw -Encoding UTF8 -LiteralPath $base15) | ConvertFrom-Json).PSObject.Properties.Name |
                         Where-Object { $_ -notmatch '^_' })
        } catch { $known15 = @() }
        # ⛔这里绝不能用 `return`：脚本级 return 会直接结束整个闸门 ⇒ 下面的"结论"与 exit 码都不执行
        #   ⇒ 收口脚本自己造出一个假绿灯（改完当轮就踩过一次，故在此留字）。
        if ($known15.Count -eq 0) {
            Bad "诱饵集基线读不出来（0 条＝$base15 解析失败或为空）⇒ 本自检不可信，不许当绿灯；先看编码／JSON 形。"
        } else {
            $newBlind = @($now15 | Where-Object { $known15 -notcontains $_ })
            $healed = @($known15 | Where-Object { $now15 -notcontains $_ })
            if ($newBlind.Count -gt 0) {
                Bad "诱饵集：本次改动闸门后出现**基线外新盲区** $((($newBlind | Sort-Object) -join '、'))（基线 $($known15.Count) 条）⇒ 判据被改盲了，须复核改动。"
            } elseif ($healed.Count -gt 0) {
                Ok "诱饵集：基线内 $((($healed | Sort-Object) -join '、')) 条盲区已消失＝判据修好了 ⇒ 请把 已知盲区.json 对应行删掉（留着＝免检牌）。"
            } else {
                Ok "诱饵集：改闸门后盲区集与基线一致（$($known15.Count) 条：$((($now15 | Sort-Object) -join '、'))）。"
            }
        }
    }
}

Write-Host ""
Write-Host "[NOTE] 闸12—14 的未覆盖面（照实声明，不假称闭环）：①§二.16 第④款「换窗判据」属语义判断，无机器判据；②坑 044 **丙型＝拿条目标题判条文存在性**，grep 类闸门结构上抓不到（它的问题不是用词，是**检索选错了层**），只能靠"立／改规则前先读该章正文"这一动作——现由 §二.16① 的"正向自检"＋法师人工复核兜，**无闸**。若要真闸，须先在规约里定"引用某规则前须 Read 该节全文"的可核验痕迹面，候法师再示。" -ForegroundColor Gray

# ---------- 结论 ----------
Write-Host ""
if ($warn -gt 0) {
    Write-Host "结论：[收口未完] $warn 项告警。补齐后重跑本脚本；确属可豁免项（如纯执行轮无需 D 编号），在收口说明中写明理由。" -ForegroundColor Yellow
    exit 2
} else {
    Write-Host "结论：[收口要件齐] 可关窗/交付。" -ForegroundColor Green
    exit 0
}
