$ErrorActionPreference = 'Stop'
$python = Get-Command python -ErrorAction Stop
$utkRoot = Join-Path $env:LOCALAPPDATA 'UltraTokenKiller'
$venv = Join-Path $utkRoot 'venv'
& $python.Source -m venv $venv
$venvPython = Join-Path $venv 'Scripts\python.exe'
$source = Resolve-Path (Join-Path $PSScriptRoot '..')
& $venvPython -m pip install --upgrade --constraint (Join-Path $source 'constraints.txt') $source
& $venvPython -m ultratokenkiller.cli install
