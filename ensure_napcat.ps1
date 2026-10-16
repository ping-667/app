$ErrorActionPreference = 'Stop'
function Test-NapCatReady {
    try {
        $r = Invoke-WebRequest 'http://127.0.0.1:6099/webui/' -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200 -and $r.Content -match 'NapCat'
    } catch { return $false }
}
if (Test-NapCatReady) { exit 0 }
if (-not (Test-Path -LiteralPath 'E:\NapCatNode\node.exe')) { throw 'NapCat runtime missing: E:\NapCatNode' }
Start-Process 'E:\NapCatNode\node.exe' -ArgumentList 'index.js' -WorkingDirectory 'E:\NapCatNode' -WindowStyle Hidden
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    if (Test-NapCatReady) { exit 0 }
}
throw 'NapCat startup timed out. Check E:\NapCatNode\napcat\logs.'
