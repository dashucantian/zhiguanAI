# 定时拉起 DSH web（法师 2026-10-21 09:2x 准「甲：每 2 小时拉起 dsh --profile web」）
# 设计取舍（照实写在件内，免得后人问）：
#  1) `dsh --profile web` 是**起一个 Web 服务**（--host/--port/--no-open），不是起界面进程；
#     直接每 2 小时裸跑会在端口已占时反复失败刷日志 ⇒ 本件**先探端口**：在跑就只记一行，不在跑才拉。
#  2) 用 --no-open，避免每 2 小时弹一次浏览器。
#  3) 全部结果只追加到 _analysis_tmp\dsh_web_wake.log，不改任何项目件。
#  4) 本件为库外件（*.ps1 被 .gitignore:79 忽略；法师 -f 白名单只准过三件），换机需重建——
#     任务名与命令见 `01_项目管理/交接试跑_20261019/DSH-fc2ce735/20261021_定时拉起DSHweb_建单记录_v1.md`。
param([int]$Port = 48000, [switch]$DryRun)
$log = 'D:\Project\zhiguanAI\_analysis_tmp\dsh_web_wake.log'
$ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
function L($m) { Add-Content -LiteralPath $log -Value ("[{0}] {1}" -f $ts, $m) -Encoding UTF8 }
$alive = $false
try {
  $c = New-Object System.Net.Sockets.TcpClient
  $ok = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
  $alive = $ok.AsyncWaitHandle.WaitOne(800) -and $c.Connected
  $c.Close()
} catch { $alive = $false }
if ($alive) { L ("已在跑：127.0.0.1:{0} 可连 ⇒ 本次不拉（幂等）" -f $Port); exit 0 }
if ($DryRun) { L ("DryRun：端口 {0} 不通，正式运行时会执行 dsh --profile web --no-open --port {0}" -f $Port); exit 0 }
try {
  Start-Process -FilePath 'dsh.cmd' -ArgumentList '--profile','web','--no-open','--port',"$Port" -WindowStyle Hidden -ErrorAction Stop
  L ("已拉起：dsh --profile web --no-open --port {0}（端口先前不通）" -f $Port)
} catch {
  L ("拉起失败：{0}" -f $_.Exception.Message)
  exit 1
}