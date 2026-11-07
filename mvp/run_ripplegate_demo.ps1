param(
  [int]$Port = 8766
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

Write-Host "Starting RippleGate demo at http://127.0.0.1:$Port"
Write-Host "Public snapshot default; synthetic error packet selectable in the UI. Press Ctrl+C to stop."
python .\ripplegate_server.py --host 127.0.0.1 --port $Port
