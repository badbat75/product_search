$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $ProjectDir ".venv"

Write-Host "Setting up virtual environment in $VenvDir"

# Create venv if it doesn't exist
if (Test-Path $VenvDir) {
    Write-Host "Virtual environment already exists. Delete .venv and re-run to recreate." -ForegroundColor Red
    exit 1
}

python -m venv $VenvDir

# Activate
$ActivateScript = Join-Path $VenvDir "Scripts" "Activate.ps1"
& $ActivateScript

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
python -m pip install selenium anthropic pandas

# Copy config template if config doesn't exist
$ConfigFile = Join-Path $ProjectDir "conf" "search.cfg"
$ConfigTemplate = Join-Path $ProjectDir "conf" "search.cfg.template"
if (-not (Test-Path $ConfigFile)) {
    Copy-Item $ConfigTemplate $ConfigFile
    Write-Host ""
    Write-Host "Created conf/search.cfg from template — edit it to set your CLAUDE_API_KEY." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. Activate the environment with:"
Write-Host "  .venv\Scripts\Activate.ps1" -ForegroundColor Cyan
