# 开工前闸门（只读检查 · 不修改任何文件）
# 用法：powershell -ExecutionPolicy Bypass -File .\开工前检查.ps1
#       可选：-Files 'path1','path2'  只检查本次拟改的文件是否已被 git 跟踪
# 退出码：0 = 工作区干净可动手；1 = 有未提交变更或身份异常，须先处理

param(
    [string[]]$Files = @()
)

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

# powershell -File 传参时 'a','b' 会变成单个字符串 "a,b"，须再拆一次
if ($Files.Count -gt 0) {
    $Files = @($Files | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

function Write-Section($title) {
    Write-Host ""
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

Write-Host "止观AI 开工前闸门（只读）" -ForegroundColor White
Write-Host "依据：《AI代理身份登记》§八 并发四纪律；台账 KZ-013 事故根因" -ForegroundColor DarkGray

# ---------- 1. 工作区状态 ----------
Write-Section "1. 工作区状态（并发纪律①④：有他人未提交变更则停下报告，不覆盖）"
$status = git status --porcelain
if (-not $status) {
    Write-Host "[OK] 工作区干净，无未提交变更。" -ForegroundColor Green
    $dirty = $false
} else {
    $dirty = $true
    $modified = @($status | Where-Object { $_ -match '^.[MD]' })
    $untracked = @($status | Where-Object { $_ -match '^\?\?' })
    Write-Host "[警告] 工作区存在未提交变更：已跟踪文件改动 $($modified.Count) 项，未跟踪新文件 $($untracked.Count) 项。" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "已跟踪文件的改动（须确认是否本窗口所为）：" -ForegroundColor Yellow
    if ($modified.Count -gt 0) {
        $modified | ForEach-Object { Write-Host "  $_" }
        Write-Host ""
        Write-Host "→ 若上述改动非本窗口产生：按并发纪律④【停下报告，不覆盖】。" -ForegroundColor Red
        Write-Host "→ 禁用 git add . / git commit -a（会把他人未完成改动一起提交、归因错误）。" -ForegroundColor Red
        Write-Host "→ 只 git add 自己文件的显式路径。" -ForegroundColor Red
    } else {
        Write-Host "  （无）"
    }
}

# ---------- 2. 拟改文件的跟踪状态 ----------
Write-Section "2. 拟改文件是否已被 git 跟踪（未跟踪 = clone 不到，规则无法传播）"
if ($Files.Count -eq 0) {
    Write-Host "[提示] 未指定 -Files，跳过本项。建议：.\开工前检查.ps1 -Files '01_项目管理\xxx.md'" -ForegroundColor DarkGray
} else {
    foreach ($f in $Files) {
        $tracked = git ls-files -- $f
        $exists = Test-Path -LiteralPath $f
        if ($tracked) {
            Write-Host "[已跟踪] $f" -ForegroundColor Green
        } elseif ($exists) {
            Write-Host "[未跟踪·文件存在] $f  → 改后须 git add 入库" -ForegroundColor Yellow
        } else {
            Write-Host "[不存在] $f" -ForegroundColor Red
        }
    }
}

# ---------- 3. git 身份配置 ----------
Write-Section "3. git 身份配置（KZ-011：历史 41 次曾错署法师账号）"
$localName = git config --local user.name
$localEmail = git config --local user.email
Write-Host "仓库本地 user.name  = $localName"
Write-Host "仓库本地 user.email = $localEmail"
$identityBad = $false
if ($localName -match 'dashucantian') {
    $identityBad = $true
    Write-Host "[异常] 本地身份仍是法师 GitHub 账号 → AI 提交会错署法师。" -ForegroundColor Red
    Write-Host "       按《AI代理身份登记》§五：本地应为中性占位 zhiguanAI-agent，" -ForegroundColor Red
    Write-Host "       提交时显式 -c user.name='AI-00N·名称(模型)' 作 committer。" -ForegroundColor Red
} elseif ($localName -match 'zhiguanAI-agent') {
    Write-Host "[OK] 中性占位身份。提交时须显式指定 committer 与 --author。" -ForegroundColor Green
} else {
    Write-Host "[提示] 身份非预期值，请对照《AI代理身份登记》§三 登记表确认。" -ForegroundColor Yellow
}
$globalName = git config --global user.name
Write-Host "全局 user.name = $globalName  （只改 --local，不得动 --global）" -ForegroundColor DarkGray

# ---------- 4. 规则文档是否在位 ----------
Write-Section "4. 规则文档在位性（缺一即规则传播失败）"
$ruleDocs = @(
    'AI-开工入口.md',
    '01_项目管理/书稿勘误与订正台账.md',
    '01_项目管理/AI代理身份登记.md',
    '01_项目管理/止观AI项目分工与决策日志.md',
    '01_项目管理/止观AI词汇命名映射表.md',
    '01_项目管理/20260910_模型与工具路由表_v1.md'
)
$missing = 0
foreach ($d in $ruleDocs) {
    if (Test-Path -LiteralPath $d) {
        $t = git ls-files -- $d
        $tag = if ($t) { '已入库' } else { '未入库(clone不到)' }
        $color = if ($t) { 'Green' } else { 'Yellow' }
        Write-Host "[$tag] $d" -ForegroundColor $color
        if (-not $t) { $missing++ }
    } else {
        Write-Host "[缺失] $d" -ForegroundColor Red
        $missing++
    }
}
$panFiles = @(Get-ChildItem -LiteralPath '01_项目管理\案例库\决策判语' -Filter '*.md' -ErrorAction SilentlyContinue)
$panCount = $panFiles.Count
if ($panCount -eq 0) {
    Write-Host "[警告] 决策判语目录读不到（路径不存在或权限问题）→ 规约§一.2 的判语清单无法核对。" -ForegroundColor Yellow
} else {
    Write-Host "决策判语实际条数：$panCount （规约§一.2 称 13 条；若不符，以实际为准并更新规约）" -ForegroundColor DarkGray
}

# ---------- 5. 提醒 ----------
Write-Section "5. 动手前最后三条提醒"
Write-Host "① 涉文本订正（含法师订正裁定表述）：台账登记 KZ + 文档内就地注记，两处都做。" -ForegroundColor White
Write-Host "② 新规则落地三同步：①写规则文档 ②写 MEMORY.md 索引 ③强制动作写本规约。缺一视为未落地。" -ForegroundColor White
Write-Host "③ 判定权边界：义理／密级定级／对外发布／当事人处置一律上交法师；AI 不自行改法师语。" -ForegroundColor White

# ---------- 结论 ----------
Write-Host ""
if ($dirty -or $identityBad) {
    Write-Host "结论：[不可直接动手] 存在未提交变更或身份异常，先处理并报告法师。" -ForegroundColor Red
    exit 1
} else {
    Write-Host "结论：[可以动手] 工作区干净、身份正常。改后记得即提交。" -ForegroundColor Green
    exit 0
}
