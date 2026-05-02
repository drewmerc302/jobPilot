# Fetch Typst binaries on Windows.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/fetch_typst.ps1 [-Version v0.14.2]

[CmdletBinding()]
param(
    [string]$Version = "v0.14.2"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
python "$PSScriptRoot/fetch_typst.py" --version $Version
