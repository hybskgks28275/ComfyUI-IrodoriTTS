param(
    [string]$ComfyRoot = 'D:\tools\ComfyUI\ComfyUI',
    [string]$Python = 'D:\tools\ComfyUI\venv\Scripts\python.exe',
    [switch]$Quantized
)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$customNodes = Join-Path $ComfyRoot 'custom_nodes'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python not found: $Python" }
if (-not (Test-Path -LiteralPath $customNodes -PathType Container)) { throw "custom_nodes not found: $customNodes" }
$linkPath = Join-Path $customNodes 'ComfyUI-IrodoriTTS'
if (Test-Path -LiteralPath $linkPath) {
    $existing = Get-Item -LiteralPath $linkPath
    if ($existing.LinkType -ne 'Junction' -or [string]$existing.Target -ne $repoPath) {
        throw "The installation path already exists and is not this repository's junction: $linkPath"
    }
}
& $Python -m pip install -r (Join-Path $repoPath 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if ($Quantized) {
    & $Python -m pip install -r (Join-Path $repoPath 'requirements-quantized.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Quantized dependency installation failed.' }
}
if (-not (Test-Path -LiteralPath $linkPath)) {
    New-Item -ItemType Junction -Path $linkPath -Target $repoPath | Out-Null
}
Write-Output "Installed: $linkPath -> $repoPath"
Write-Output 'Restart ComfyUI, then add Irodori TTS Generate.'
