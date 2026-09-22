<#
  Passport Auto - installer

  One-line (recommended):
    iex (irm https://raw.githubusercontent.com/<user>/<repo>/main/install.ps1)

  From a zip:
    iex "& { $(irm https://raw.githubusercontent.com/<user>/<repo>/main/install.ps1) } -Zip https://<host>/passport-auto.zip"

  Local checkout:
    powershell -ExecutionPolicy Bypass -File install.ps1
#>
param(
  [string]$Zip = "",
  [string]$Dir = "$env:USERPROFILE\Desktop\Passport Auto"
)

$ErrorActionPreference = 'Stop'
function Say($m) { Write-Host "  $m" }

Write-Host ""
Write-Host "  PASSPORT AUTO" -ForegroundColor Cyan
Write-Host "  -------------" -ForegroundColor DarkGray

# ---------- 1. get the source tree ----------
# When this script is piped through iex (irm ...) there is no $PSScriptRoot, so
# fall back to downloading the repository archive automatically.
$REPO_ZIP = 'https://github.com/op-sihab/passport-auto/archive/refs/heads/main.zip'

if (-not $Zip) {
  if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'src'))) {
    $root = $PSScriptRoot
    Say "source: $root (local)"
  } else {
    $Zip = $REPO_ZIP
  }
}

if (-not $root) {
  $tmp = Join-Path $env:TEMP ("pa_" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp -Force | Out-Null
  Say "downloading the program..."
  $pkg = Join-Path $tmp "pkg.zip"
  try {
    Invoke-WebRequest -Uri $Zip -OutFile $pkg -UseBasicParsing
  } catch {
    Write-Host "  ! download failed: $_" -ForegroundColor Red
    Write-Host "    check your internet connection and run this again." -ForegroundColor Yellow
    return
  }
  try {
    Expand-Archive -Path $pkg -DestinationPath $tmp -Force
  } catch {
    Write-Host "  ! could not unpack the download: $_" -ForegroundColor Red
    return
  }
  $found = Get-ChildItem $tmp -Recurse -Filter 'pipeline_watcher.py' -ErrorAction SilentlyContinue |
           Select-Object -First 1
  if ($found) {
    $root = Split-Path (Split-Path $found.FullName -Parent) -Parent
  } else {
    Write-Host "  ! the downloaded package looks wrong (no sources inside)" -ForegroundColor Red
    return
  }
  Say "source: downloaded"
}

# ---------- 2. python (install it automatically if missing) ----------
function Find-Python {
  $p = (Get-Command python -ErrorAction SilentlyContinue).Source
  if ($p -and $p -notmatch 'WindowsApps') { return $p }
  foreach ($v in @('313','312','311','310')) {
    $c = "$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe"
    if (Test-Path $c) { return $c }
  }
  return $null
}

$pyExe = Find-Python

if (-not $pyExe) {
  Write-Host "  python not found - installing it for you" -ForegroundColor Yellow
  Say "this takes a few minutes the first time"

  $installed = $false

  # a) winget (built into Windows 11 and most Windows 10 machines)
  $wg = (Get-Command winget -ErrorAction SilentlyContinue).Source
  if ($wg) {
    Say "trying winget..."
    & $wg install -e --id Python.Python.3.12 --accept-source-agreements `
        --accept-package-agreements --silent --scope user 2>&1 | Out-Null
    Start-Sleep -Seconds 3
    $pyExe = Find-Python
    if ($pyExe) { $installed = $true; Say "python installed via winget" }
  }

  # b) fall back to the official python.org installer, fully silent
  if (-not $installed) {
    Say "falling back to the official installer from python.org"
    $ver = '3.12.10'
    $url = "https://www.python.org/ftp/python/$ver/python-$ver-amd64.exe"
    $exe = Join-Path $env:TEMP "python-$ver-amd64.exe"
    try {
      Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
      Start-Process -FilePath $exe -Wait -ArgumentList `
        '/quiet','InstallAllUsers=0','PrependPath=1','Include_pip=1',
        'Include_test=0','Include_launcher=1','Include_doc=0','Include_tcltk=1'
      Start-Sleep -Seconds 3
      $pyExe = Find-Python
      if ($pyExe) { $installed = $true; Say "python installed from python.org" }
    } catch {
      Write-Host "  ! automatic install failed: $_" -ForegroundColor Red
    }
  }

  if (-not $installed -or -not $pyExe) {
    Write-Host ""
    Write-Host "  Could not install Python automatically." -ForegroundColor Red
    Write-Host "  Install it by hand from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  (tick 'Add python.exe to PATH' during setup), then run this again." -ForegroundColor Yellow
    return
  }
}

Say "python: $pyExe"

# make sure pip + the two libraries are present
Say "installing python packages (requests, pillow)..."
& $pyExe -m ensurepip --upgrade 2>&1 | Out-Null
& $pyExe -m pip install --quiet --upgrade pip 2>&1 | Out-Null
& $pyExe -m pip install --quiet --disable-pip-version-check requests pillow 2>&1 | Out-Null
& $pyExe -c "import requests, PIL" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "  ! python packages failed to install - check your internet connection" -ForegroundColor Yellow
}

# ---------- 3. flatten into the install dir ----------
New-Item -ItemType Directory -Path $Dir -Force | Out-Null
foreach ($sub in @('src','scripts','assets','launchers')) {
  $p = Join-Path $root $sub
  if (Test-Path $p) { Copy-Item (Join-Path $p '*') $Dir -Recurse -Force }
}
foreach ($d in @('INPUT','CROPPED','FINAL','DONE','FAILED')) {
  New-Item -ItemType Directory -Path (Join-Path $Dir $d) -Force | Out-Null
}
Say "installed to $Dir"

# ---------- 4. config ----------
$setEx = Join-Path $root 'config\settings.example.json'
if ((Test-Path $setEx) -and -not (Test-Path (Join-Path $Dir 'settings.json'))) {
  Copy-Item $setEx (Join-Path $Dir 'settings.json')
}
$secEx = Join-Path $root 'config\secrets.example.json'
if ((Test-Path $secEx) -and -not (Test-Path (Join-Path $Dir 'secrets.json'))) {
  Copy-Item $secEx (Join-Path $Dir 'secrets.json')
  Write-Host "  ! edit secrets.json and add your API keys, then restart" -ForegroundColor Yellow
}

# ---------- 5. shortcuts, notification icon, autostart ----------
foreach ($s in @('make_shortcuts.ps1','register_appid.ps1')) {
  $p = Join-Path $Dir $s
  if (Test-Path $p) {
    Say "running $s"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $p | Out-Null
  }
}

# ---------- 6. first run: ask for the API keys, then start ----------
$pa  = Join-Path $Dir 'pa.py'
$sec = Join-Path $Dir 'secrets.json'

function Test-Keys {
  if (-not (Test-Path $sec)) { return $false }
  try {
    $j = Get-Content $sec -Raw | ConvertFrom-Json
    foreach ($k in @('fireworks_api_key','cun_api_key')) {
      $v = $j.$k
      if (-not $v -or $v -match 'your_') { return $false }
    }
    return $true
  } catch { return $false }
}

if (Test-Path $pa) {
  if (-not (Test-Keys)) {
    Write-Host ""
    Write-Host "  STEP 1 of 2 - enter your API keys" -ForegroundColor Yellow
    Write-Host "  (you can redo this later with:  $Dir\pa.cmd setup)" -ForegroundColor DarkGray
    & $pyExe $pa setup
  }
  Write-Host "  STEP 2 of 2 - starting the watcher" -ForegroundColor Yellow
  & $pyExe $pa start
}

Write-Host ""
Write-Host "  DONE" -ForegroundColor Green
Say "drop photos into  : $Dir\INPUT"
Say "collect finished  : $Dir\FINAL"
Say "control panel     : double-click 'Passport Auto TUI.cmd'"
Say "desktop shortcuts : '1 - Drop Photo Here' / '2 - Get Finished Photos' / '3 - Status'"
Write-Host ""
Write-Host "  It starts automatically every time Windows starts." -ForegroundColor DarkGray
Write-Host ""
