<#
.SYNOPSIS
  Brompt Engine — build, test, and run commands for Windows (PowerShell).
.EXAMPLE
  .\brompt.ps1 install      # full install with all extras
  .\brompt.ps1 test         # run all unit tests
  .\brompt.ps1 test-api     # run API tests only
  .\brompt.ps1 run          # start the REST API server
  .\brompt.ps1 cli          # launch CLI TUI
  .\brompt.ps1 widget       # launch floating widget (no console)
  .\brompt.ps1 clean        # remove caches
#>

param (
  [Parameter(Position = 0)]
  [ValidateSet("install", "test", "test-api", "test-feedback", "run", "cli", "widget", "clean")]
  [string]$Command
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Command) {
  "install" {
    Write-Host "Installing Brompt Engine with all extras..." -ForegroundColor Cyan
    & pip install -e "$root\[dev,api,all]" --quiet
    Write-Host "Done." -ForegroundColor Green
  }
  "test" {
    Write-Host "Running all unit tests..." -ForegroundColor Cyan
    $env:PYTHONPATH = "$root\src"
    & python -m pytest "$root\tests" -v --ignore="$root\tests\test_integration.py"
  }
  "test-api" {
    Write-Host "Running API tests..." -ForegroundColor Cyan
    $env:PYTHONPATH = "$root\src"
    & python -m pytest "$root\tests\test_api.py" -v
  }
  "test-feedback" {
    Write-Host "Running feedback loop tests..." -ForegroundColor Cyan
    $env:PYTHONPATH = "$root\src"
    & python -m pytest "$root\tests\test_feedback_loop.py" -v
  }
  "run" {
    Write-Host "Starting Brompt API server..." -ForegroundColor Cyan
    $env:PYTHONPATH = "$root\src"
    & uvicorn brompt.api.routes:app --reload --host 0.0.0.0 --port 8000
  }
  "cli" {
    Write-Host "Launching CLI TUI..." -ForegroundColor Cyan
    $env:PYTHONPATH = "$root\src"
    & python -m brompt.cli
  }
  "widget" {
    Write-Host "Launching floating widget (no console window)..." -ForegroundColor Cyan
    $env:PYTHONPATH = "$root\src"
    & pythonw -m brompt.guiapp --live
  }
  "clean" {
    Write-Host "Cleaning caches..." -ForegroundColor Cyan
    $dirs = @(
      "$root\.pytest_cache"
      "$root\__pycache__"
      "$root\src\__pycache__"
      "$root\src\brompt\__pycache__"
      "$root\src\brompt\feedback\__pycache__"
      "$root\src\brompt\api\__pycache__"
      "$root\tests\__pycache__"
    )
    foreach ($d in $dirs) {
      if (Test-Path $d) { Remove-Item -Recurse -Force $d }
    }
    Get-ChildItem -Path $root -Recurse -Filter "*.pyc" | Remove-Item -Force
    Write-Host "Done." -ForegroundColor Green
  }
  default {
    Get-Content $MyInvocation.MyCommand.Path | Select-String -Pattern "^  .*#" | ForEach-Object {
      $_.ToString().Trim()
    }
  }
}
