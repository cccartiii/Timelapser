<#
.SYNOPSIS
    Builds Timelapser.exe.

.DESCRIPTION
    Installs dependencies and runs PyInstaller. Every path - the work
    directory, the dist directory and the onefile unpack directory - is kept on
    this drive, because the system drive has almost no free space.
#>

[CmdletBinding()]
param(
    [switch]$SkipDeps,
    [switch]$Console  # build with a console window, useful for diagnosing startup errors
)

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

$AppDataRoot = Join-Path $ProjectDir '.build'
$DistPath = Join-Path $AppDataRoot 'dist'
$WorkPath = Join-Path $AppDataRoot 'build'
$RuntimeTmp = Join-Path $AppDataRoot 'runtime-tmp'
$LegacyScratch = Join-Path $AppDataRoot 'scratch'

New-Item -ItemType Directory -Force -Path $AppDataRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DistPath | Out-Null
New-Item -ItemType Directory -Force -Path $WorkPath | Out-Null
New-Item -ItemType Directory -Force -Path $RuntimeTmp | Out-Null
New-Item -ItemType Directory -Force -Path $LegacyScratch | Out-Null

Write-Host "Project     : $ProjectDir" -ForegroundColor Cyan
Write-Host "Dist        : $DistPath" -ForegroundColor Cyan
Write-Host "Work        : $WorkPath" -ForegroundColor Cyan
Write-Host "Runtime tmp : $RuntimeTmp" -ForegroundColor Cyan

$drive = (Get-Item $ProjectDir).PSDrive.Name
$free = (Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${drive}:'").FreeSpace
Write-Host ("Free space  : {0:N1} GB on {1}:" -f ($free / 1GB), $drive) -ForegroundColor Cyan
if ($free -lt 2GB) {
    throw "Need at least 2 GB free on ${drive}: to build."
}

New-Item -ItemType Directory -Force -Path $RuntimeTmp | Out-Null

if (-not $SkipDeps) {
    Write-Host "`nInstalling dependencies..." -ForegroundColor Yellow
    python -m pip install --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'dependency install failed' }
}

Write-Host "`nRunning PyInstaller..." -ForegroundColor Yellow
$specArgs = @(
    '--noconfirm',
    '--distpath', $DistPath,
    '--workpath', $WorkPath,
    'timelapser.spec'
)
python -m PyInstaller @specArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

$exe = Join-Path $DistPath 'Timelapser.exe'
if (-not (Test-Path $exe)) { throw "expected $exe to exist" }

$sizeMB = (Get-Item $exe).Length / 1MB
Write-Host ("`nBuilt {0} ({1:N1} MB)" -f $exe, $sizeMB) -ForegroundColor Green
Write-Host "The exe unpacks to $RuntimeTmp at launch, not to %TEMP%." -ForegroundColor Green
