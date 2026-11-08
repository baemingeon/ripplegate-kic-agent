$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$teamInfoPath = Join-Path $workspace "기획서\team_info.json"
$pythonExe = if ($env:KIC_PYTHON) { $env:KIC_PYTHON } else { "C:\Users\bmg37\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" }
$nodeExe = if ($env:KIC_NODE) { $env:KIC_NODE } else { "C:\Users\bmg37\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" }
$nodeModules = "C:\Users\bmg37\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
$pptMark = "C:\Users\bmg37\.codex\plugins\cache\openai-primary-runtime\presentations\26.1105.12137\skills\presentations\container_tools\mark_artifact_operation_started.mjs"
$pdfMark = "C:\Users\bmg37\.codex\plugins\cache\openai-primary-runtime\pdf\26.1105.12137\skills\pdf\container_tools\mark_artifact_operation_started.mjs"

if (-not (Test-Path -LiteralPath $teamInfoPath)) {
    throw "기획서\team_info.json이 없습니다. team_info.template.json을 복사한 뒤 팀 정보를 입력하세요."
}

$teamInfo = Get-Content -LiteralPath $teamInfoPath -Raw | ConvertFrom-Json
$requiredFields = @("team_name", "leader", "members", "contact")
$missingFields = @($requiredFields | Where-Object {
    $value = $teamInfo.$_
    [string]::IsNullOrWhiteSpace([string]$value)
})
if ($missingFields.Count -gt 0) {
    throw "team_info.json의 입력 누락: $($missingFields -join ', ')"
}

# The draft v0.9.2 is intentionally generated with placeholders. The
# presentation finalizer does not overwrite an existing final file, so keep a
# recoverable, timestamped copy before injecting the supplied team identity.
$existingPptx = Join-Path $workspace "기획서\KIC_AI_에이전트_공모전_기획서_작업본_v0.9.2.pptx"
$existingPdf = Join-Path $workspace "기획서\KIC_AI_에이전트_공모전_기획서_작업본_v0.9.2.pdf"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$placeholderBackupDir = Join-Path $workspace ".codex-build\pre-team-final-v091-$timestamp"
$placeholderBackup = Join-Path $placeholderBackupDir "KIC_AI_에이전트_공모전_기획서_작업본_v0.9.2.previous.pptx"
$receiptPath = Join-Path $workspace ".codex-finalizer-v09.2\validation.json"
if (Test-Path -LiteralPath $existingPptx) {
    New-Item -ItemType Directory -Path $placeholderBackupDir -Force | Out-Null
    Move-Item -LiteralPath $existingPptx -Destination $placeholderBackup
}
if (Test-Path -LiteralPath $existingPdf) {
    New-Item -ItemType Directory -Path $placeholderBackupDir -Force | Out-Null
    Move-Item -LiteralPath $existingPdf -Destination (Join-Path $placeholderBackupDir "KIC_AI_에이전트_공모전_기획서_작업본_v0.9.2.previous.pdf")
}
if (Test-Path -LiteralPath $receiptPath) {
    New-Item -ItemType Directory -Path $placeholderBackupDir -Force | Out-Null
    Move-Item -LiteralPath $receiptPath -Destination (Join-Path $placeholderBackupDir "previous-validation.json")
}

Push-Location $workspace
try {
    $env:CODEX_PRIMARY_RUNTIME_NODE_MODULES = $nodeModules
    $env:RUNTIME_NODE_MODULES = $nodeModules
    $env:NODE_PATH = $nodeModules
    & $nodeExe $pptMark --operation-kind edit --expected-output-count 1 --output-format pptx
    & $nodeExe .codex-build\build_v03.mjs

    & $nodeExe .codex-build\finalize_v09.mjs

    & $nodeExe $pdfMark --operation-kind create --expected-output-count 1 --output-format pdf
    & $pythonExe .codex-build\export_png_pdf_v11.py
    & $pythonExe mvp\generate_pilot_artifacts.py
    & $pythonExe .codex-build\package_release_v083.py
    & $pythonExe -B mvp\validate_release.py
    & $pythonExe mvp\validate_submission.py
} finally {
    Pop-Location
}
