# =========================================================================
# Persistent In-Memory Windows Runtime OCR Daemon for Esports Telemetry
# Loads Windows.Media.Ocr.OcrEngine into RAM ONCE at startup.
# Processes subsequent recognition requests in ~10ms with zero process overhead.
# =========================================================================

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
})[0]

Function AwaitTask($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { 
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US')) 
}

# Signal Python that daemon is ready
[Console]::Out.WriteLine("READY")
[Console]::Out.Flush()

while ($line = [Console]::In.ReadLine()) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -eq 'QUIT') { break }
    if ($line -eq 'PING') {
        [Console]::Out.WriteLine("PONG")
        [Console]::Out.Flush()
        continue
    }

    if ($line.StartsWith('RECOGNIZE ')) {
        $imgPath = $line.Substring(10).Trim()
        try {
            if (-not (Test-Path $imgPath)) {
                [Console]::Out.WriteLine("ERROR:FileNotFound")
                [Console]::Out.Flush()
                continue
            }

            $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $imgPath).Path)
            $stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
            $writer = [Windows.Storage.Streams.DataWriter]::new($stream)
            $writer.WriteBytes($bytes)
            $null = AwaitTask ($writer.StoreAsync()) ([System.UInt32])
            $null = AwaitTask ($writer.FlushAsync()) ([System.Boolean])
            $stream.Seek(0)

            $decoder = AwaitTask ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap = AwaitTask ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            $result = AwaitTask ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

            # Output in compact, easy-to-parse JSON
            $outLines = @()
            if ($result.Lines) {
                foreach ($l in $result.Lines) {
                    $outWords = @()
                    foreach ($w in $l.Words) {
                        $r = $w.BoundingRect
                        $outWords += @{
                            t = $w.Text
                            x = [int]$r.X
                            y = [int]$r.Y
                            w = [int]$r.Width
                            h = [int]$r.Height
                        }
                    }
                    $outLines += @{
                        text = $l.Text
                        words = $outWords
                    }
                }
            }

            $payload = @{
                text = ($result.Text -replace '[\r\n]+', ' ')
                lines = $outLines
            }

            $jsonStr = ConvertTo-Json -Compress -InputObject $payload
            [Console]::Out.WriteLine("JSON:" + $jsonStr)
        }
        catch {
            [Console]::Out.WriteLine("ERROR:" + $_.Exception.Message)
        }
        [Console]::Out.Flush()
    }
}

