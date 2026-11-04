<#
  建worktree.ps1 —— 隔离执行脚手架（把「有条件采用」变成能用的东西）
  立据：法师 2026-11-03 字「准建 worktree」；实验结论＝有条件采用
  治的坑：081「共享工作树里没有干净起点」——worktree add 只接 HEAD，
          目标路径若有在途改动，建出来的树拿不到那些改动，工开了也白开
  性质：只建不提交；不推；不改主树工作区
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Task,      # 例 TASK-20261103-02
  [Parameter(Mandatory=$true)][string]$Path,      # 相对仓根的目标路径，例 06_宣发素材/发布队列
  [string]$Base = 'HEAD',
  [string]$WtRoot = '',                            # 缺省 <仓根>\_worktrees
  [switch]$Force                                   # 脏也建（须在回报里写明为什么）
)

$ErrorActionPreference = 'Stop'
function Fail($msg, $code) { [Console]::Error.WriteLine("[FAIL] $msg"); exit $code }
function Log($msg)  { Write-Host "[OK]   $msg" }
function Warn($msg) { Write-Host "[WARN] $msg" }

# 0. 定位仓根
try { $root = (& git rev-parse --show-toplevel 2>$null) } catch { $root = $null }
if (-not $root) { Fail 'git 探针不通：不在仓内或 git 不可用' 2 }
$root = $root.Trim()
Log "仓根 $root"

# 1. 目标路径必须存在（否则不是"路径净不净"问题，是路径写错）
$abs = Join-Path $root $Path
if (-not (Test-Path $abs)) { Fail "目标路径不在盘：$Path" 3 }
Log "目标路径 $Path 在盘"

# 2. ★ 坑 081 前置闸：目标路径必须干净
$dirty = @(& git -C $root status --porcelain -- $Path 2>$null)
if ($dirty.Count -gt 0) {
  Warn "目标路径有 $($dirty.Count) 处在途："
  $dirty | Select-Object -First 12 | ForEach-Object { Warn "    $_" }
  if (-not $Force) {
    [Console]::Error.WriteLine(@"

[拒绝建树] 目标路径不净。worktree add 只接 HEAD，
           在途改动拿不到 —— 建出来等于起点不净（坑 081）。
           三条处置，任选其一后重跑：
             甲 等该路径的在途件提交或撤回（等它干净）
             乙 换载体：换成现查 0 处脏的目录（实验首轮取的就是这条）
             丙 确实要带脏件建：加 -Force，并在回报里写明为什么与影响面
"@)
    exit 4
  }
  Warn '已 -Force：起点不净，回报里必须写明为什么这么干'
} else {
  Log '目标路径现查 0 处在途（起点干净）'
}

# 3. 记基线
$head = (& git -C $root rev-parse HEAD).Trim()
$short = (& git -C $root rev-parse --short HEAD).Trim()
Log "基线 HEAD $short"

# 4. 建树
if ([string]::IsNullOrWhiteSpace($WtRoot)) { $WtRoot = Join-Path $root '_worktrees' }
$slug = ($Task -replace '[^A-Za-z0-9\-]', '-')
$wtPath = Join-Path $WtRoot $slug
$branch = "wt/$slug"
if (Test-Path $wtPath) { Fail "worktree 路径已存在：$wtPath（先 worktree remove 或换 Task 名）" 5 }

# 原生命令往 stderr 打进度行（如 "Preparing worktree"）会被 PS 当 ErrorRecord，
# 在 $ErrorActionPreference='Stop' 下直接抛错并吞掉真退码 —— 故此处临时降级，改用显式 $LASTEXITCODE
$prevEA = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& git -C $root worktree add $wtPath -b $branch $Base 2>&1 | ForEach-Object { Write-Host "      $_" }
$rc = $LASTEXITCODE
$ErrorActionPreference = $prevEA
if ($rc -ne 0) { Fail "worktree add 退码 $rc" 6 }
Log "已建 $wtPath（分支 $branch）"

# 5. 自证四条判据（打印可复核命令，不代跑判定）
Write-Host ''
Write-Host '=== 四条判据自证命令（照此复跑；任一反例出现即判失败） ==='
Write-Host ''
Write-Host '① 主树零冲突（主树工作区不因建树而变）'
Write-Host "   git -C `"$root`" status --porcelain -- $Path"
Write-Host ''
Write-Host '② 归因三层可查（author／committer／七字段尾注）'
Write-Host "   cd `"$wtPath`"; git log -1 --format='author=%an <%ae>%ncommitter=%cn <%ce>%n%B'"
Write-Host ''
Write-Host '③ rev-parse 确在 worktree（不是主树）'
Write-Host "   cd `"$wtPath`"; git rev-parse --show-toplevel"
Write-Host ''
Write-Host '④ 可无冲突合回'
Write-Host "   git -C `"$root`" merge --no-ff $branch"
Write-Host ''
Write-Host "收工：git -C `"$root`" worktree remove `"$wtPath`" --force"
Write-Host ''
Log "建树完成｜Task=$Task｜Base=$short｜分支=$branch"
exit 0