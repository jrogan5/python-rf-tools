#Requires -Version 5.1
<#
.SYNOPSIS
    Incrementally build standalone Windows executables for RF MDIF Tools.

.DESCRIPTION
    Each executable is only rebuilt when one of its source files is newer
    than the already-built versioned .exe in dist\.  Pass -Force to rebuild
    everything regardless.

    Output (in dist\):
        rf-mdif-v<version>.exe
        rf-sort-rdi-v<version>.exe
        rf-sort-4pack-v<version>.exe

.PARAMETER Force
    Rebuild all executables even if sources have not changed.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Force
#>
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

# -- Read version -------------------------------------------------------------
$verFile = Get-Content "_version.py" -Raw
if ($verFile -notmatch '__version__\s*=\s*[''"]([^''"]+)[''"]') {
    Write-Error "Could not read __version__ from _version.py"
    exit 1
}
$defaultVersion = $Matches[1]

Write-Host ""
Write-Host " RF MDIF Tools  v$defaultVersion"
Write-Host " ============================================================"

# -- Ensure PyInstaller is installed ------------------------------------------
$null = pip show pyinstaller 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host " PyInstaller not found -- installing ..."
    pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install PyInstaller. Aborting."
        exit 1
    }
}

# -- Helper: newest .py modification time across a set of paths ---------------
function Get-NewestSourceTime {
    param([string[]]$Paths)
    $files = foreach ($p in $Paths) {
        if (Test-Path $p -PathType Leaf) {
            Get-Item $p
        } elseif (Test-Path $p -PathType Container) {
            Get-ChildItem $p -Recurse -Filter "*.py" -File
        }
    }
    $newest = @($files) | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($newest) { return $newest.LastWriteTime }
    return [datetime]::MinValue
}

# -- Helper: decide whether a given exe needs rebuilding ----------------------
function Test-NeedsRebuild {
    param([string]$ExeName, [string[]]$SourcePaths)
    if ($Force) { return $true }
    $existing = Get-Item "dist\$ExeName-v$defaultVersion.exe" -ErrorAction SilentlyContinue
    if (-not $existing) { return $true }
    $newestSource = Get-NewestSourceTime $SourcePaths
    return $newestSource -gt $existing.LastWriteTime
}

# -- Table of tools -----------------------------------------------------------
# To add a new tool: append an entry here and create specs\<spec-file>.
$tools = @(
    @{
        Name    = "rf-mdif"
        Spec    = "specs\rf_mdif.spec"
        Sources = @("data_to_mdif", "utils", "_version.py")
    }
    @{
        Name    = "rf-sort-rdi"
        Spec    = "specs\rf_sort_rdi.spec"
        Sources = @("sorting\rdi", "utils", "_version.py")
    }
    @{
        Name    = "rf-sort-4pack"
        Spec    = "specs\rf_sort_4pack.spec"
        Sources = @("sorting\4pack", "utils", "_version.py")
    }
    @{
    Name    = "rf-plot"
    Spec    = "specs\rf-plot.spec"
    Sources = @("plot", "utils", "_version.py")
}
    @{
        Name    = "rf-dbf-to-mdif"
        Spec    = "specs\rf-dbf-to-mdif.spec"
        Sources = @("dbf_to_mdif", "utils", "_version.py")
    }
    @{
        Name    = "rf-mdif-tdr"
        Spec    = "specs\rf-mdif-tdr.spec"
        Sources = @("mdif_tdr", "utils", "_version.py")
    }
)
$toBuild = @()
foreach ($t in $tools) {
    $ans = Read-Host "Build $($t.Name)? [Y/n]"
    if ($ans -match '^[Nn]') { continue }

    $verPrompt = Read-Host "Version to use for $($t.Name) (blank = $defaultVersion)"
    $buildVer = if ($verPrompt) { $verPrompt } else { $defaultVersion }
    $t | Add-Member -NotePropertyName BuildVersion -NotePropertyValue $buildVer
    $toBuild += $t
}

if ($toBuild.Count -eq 0) {
    Write-Host ""
    Write-Host " No tools selected for build."
    Write-Host " ============================================================"
    exit 0
}



# -- Clean the PyInstaller work directory (not dist\) -------------------------
# dist\ is left intact so up-to-date versioned exes are not removed.
if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
}

# -- Build only what has changed ----------------------------------------------
$failed = $false

foreach ($t in $toBuild) {
    Write-Host ""
    Write-Host " Building $($t.Name) ..."

    python -m PyInstaller $t.Spec
    if ($LASTEXITCODE -ne 0) {
        Write-Host " ERROR: build failed for $($t.Name)."
        $failed = $true
        continue
    }

    $src = "dist\$($t.Name).exe"
    $dst = "dist\$($t.Name)-v$($t.BuildVersion).exe"
    if (Test-Path $dst) { Remove-Item $dst -Force }
    Move-Item -Path $src -Destination $dst -Force
    Write-Host " -> $dst"
}

if ($failed) {
    Write-Error "One or more builds failed -- see output above."
    exit 1
}

# -- Summary ------------------------------------------------------------------
Write-Host ""
Write-Host " ============================================================"
Write-Host " Build complete.  Current executables in dist\:"
Write-Host ""
Get-ChildItem "dist\*.exe" | ForEach-Object { Write-Host "   $($_.Name)" }
Write-Host ""
Write-Host " ============================================================"
