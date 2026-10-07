# Windows 自带 OCR 桥接（零安装）。法师 2026-10-07 金口：屏幕内容本机脱敏后才可出网。
# 只做一件事：读一张 PNG，把 OCR 行/词与**词级坐标**吐成 UTF-8 JSON（不含 BOM）。
# 用法：设 OCIN=图片路径 OCOUT=输出 JSON 路径，然后 powershell -File ocr_lines.ps1
# 注意：本文件正文一律 ASCII（Windows PowerShell 5.1 读 UTF-8 无 BOM 会把非 ASCII 读错）。
# 实测坑两条，勿再踩：
#   1) OcrLine 没有 BoundingRect（取到的是 null）——坐标只在 OcrWord 级。
#   2) PowerShell 5.1 必须先以限定语法把 WinRT 类型投影进会话，裸 [Namespace.Type] 报"找不到类型"。
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                   $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await($op, $T) {
    $m = $asTaskGeneric.MakeGenericMethod($T)
    $t = $m.Invoke($null, @(, $op))
    [void]$t.Wait(-1)
    return $t.Result
}

$TDec = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$TBmp = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$TOcr = [Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType=WindowsRuntime]
$TEng = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime]
$TLang = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]

$path = $env:OCIN
$out = $env:OCOUT
if (-not $path -or -not $out) { Write-Error 'OCIN/OCOUT not set'; exit 3 }

$fs = [System.IO.File]::OpenRead($path)
try {
    $ras = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($fs)
    $dec = Await ($TDec::CreateAsync($ras)) $TDec
    $bmp = Await ($dec.GetSoftwareBitmapAsync()) $TBmp

    $eng = $TEng::TryCreateFromUserProfileLanguages()
    if ($null -eq $eng) {
        $lang = [activator]::CreateInstance($TLang, [string]'zh-Hans-CN')
        $eng = $TEng::TryCreateFromLanguage($lang)
    }
    if ($null -eq $eng) { Write-Output 'OCR-ENGINE=NULL'; exit 2 }

    $res = Await ($eng.RecognizeAsync($bmp)) $TOcr

    $lines = @()
    foreach ($ln in $res.Lines) {
        $ws = @()
        foreach ($w in $ln.Words) {
            $r = $w.BoundingRect
            $ws += [pscustomobject]@{ t = $w.Text; x = [math]::Round($r.X, 1); y = [math]::Round($r.Y, 1);
                                      w = [math]::Round($r.Width, 1); h = [math]::Round($r.Height, 1) }
        }
        $lines += [pscustomobject]@{ text = $ln.Text; words = $ws }
    }
    $doc = [pscustomobject]@{ ok = $true; engine = $eng.RecognizerLanguage.LanguageTag;
                              imgW = $bmp.PixelWidth; imgH = $bmp.PixelHeight;
                              lineCount = $lines.Count; lines = $lines }
    [System.IO.File]::WriteAllText($out, (ConvertTo-Json $doc -Compress -Depth 5),
                                   (New-Object System.Text.UTF8Encoding($false)))
    Write-Output ('OK LINES=' + $lines.Count)
} finally {
    $fs.Dispose()
}
