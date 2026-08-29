# Text recognition for radio_tracklog.py's watch mode on Windows, using the
# OCR engine built into Windows 10/11 (Windows.Media.Ocr) — on-device, offline,
# nothing to install. Run by the script through the stock Windows PowerShell:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 <image>
#
# Prints exactly what ocr.swift prints on macOS, one line per recognized text:
#   "<x> <y> <width>\t<text>"
# x/y = the text's position as fractions of the frame measured from the
# BOTTOM-LEFT corner, width = the text's width as a fraction of the frame.

param([Parameter(Mandatory = $true)][string]$ImagePath)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8   # names like MØØNE survive the pipe
$inv = [System.Globalization.CultureInfo]::InvariantCulture # "0.123", never "0,123"

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics,ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams,ContentType=WindowsRuntime]

# WinRT calls are async; this turns an IAsyncOperation<T> into its result.
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
function Await($op, $resultType) {
    $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    return $task.Result
}

$path = (Resolve-Path -LiteralPath $ImagePath).Path
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en"))
}
if (-not $engine) {
    [Console]::Error.WriteLine("No Windows OCR language available — add a language pack in Settings > Time & Language.")
    exit 1
}

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$W = [double]$bitmap.PixelWidth
$H = [double]$bitmap.PixelHeight
foreach ($line in $result.Lines) {
    $left = [double]::MaxValue; $right = 0.0; $bottom = 0.0
    foreach ($word in $line.Words) {
        $r = $word.BoundingRect
        if ($r.X -lt $left) { $left = $r.X }
        if ($r.X + $r.Width -gt $right) { $right = $r.X + $r.Width }
        if ($r.Y + $r.Height -gt $bottom) { $bottom = $r.Y + $r.Height }
    }
    if ($right -le $left) { continue }
    $x = ($left / $W).ToString("F3", $inv)
    $y = (1.0 - $bottom / $H).ToString("F3", $inv)      # from the bottom edge, like Vision
    $w = (($right - $left) / $W).ToString("F3", $inv)
    Write-Output ("{0} {1} {2}`t{3}" -f $x, $y, $w, $line.Text)
}
