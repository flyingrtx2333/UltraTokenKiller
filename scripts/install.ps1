$ErrorActionPreference = 'Stop'
$python = Get-Command python -ErrorAction Stop
$utkRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'UltraTokenKiller'))
$active = [IO.Path]::GetFullPath((Join-Path $utkRoot 'venv'))
$staging = [IO.Path]::GetFullPath((Join-Path $utkRoot 'venv.new'))
$previous = [IO.Path]::GetFullPath((Join-Path $utkRoot 'venv.previous'))
$source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

foreach ($target in @($active, $staging, $previous)) {
    if (-not $target.StartsWith($utkRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe runtime path: $target"
    }
}
New-Item -ItemType Directory -Force -Path $utkRoot | Out-Null
if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
& $python.Source -m venv $staging
$stagingPython = Join-Path $staging 'Scripts\python.exe'
& $stagingPython -m pip install --upgrade --constraint (Join-Path $source 'constraints.txt') $source
& $stagingPython -m ultratokenkiller.cli capabilities | Out-Null
if ($env:UTK_SKIP_ASSETS -ne '1') {
    $env:UTK_HOME = $utkRoot
    & $stagingPython -m ultratokenkiller.cli assets install
}

if (Test-Path -LiteralPath $previous) { Remove-Item -LiteralPath $previous -Recurse -Force }
if (Test-Path -LiteralPath $active) { Move-Item -LiteralPath $active -Destination $previous }
Move-Item -LiteralPath $staging -Destination $active
$activePython = Join-Path $active 'Scripts\python.exe'
try {
    & $activePython -m ultratokenkiller.cli install
    if ($LASTEXITCODE -ne 0) { throw "UTK install returned $LASTEXITCODE" }
} catch {
    if (Test-Path -LiteralPath $active) { Remove-Item -LiteralPath $active -Recurse -Force }
    if (Test-Path -LiteralPath $previous) { Move-Item -LiteralPath $previous -Destination $active }
    throw "UTK installation failed; previous runtime restored. $($_.Exception.Message)"
}
Write-Host "UTK installed. Previous runtime retained at $previous for rollback."
