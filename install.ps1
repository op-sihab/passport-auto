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
if ($Zip) {
  $tmp = Join-Path $env:TEMP ("pa_" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp -Force | Out-Null
  Say "downloading payload..."
  $pkg = Join-Path $tmp "pkg.zip"
  Invoke-WebRequest -Uri $Zip -OutFile $pkg -UseBasicParsing
  Expand-Archive -Path $pkg -DestinationPath $tmp -Force
  $root = Get-ChildItem $tmp -Recurse -Filter 'pipeline_watcher.py' -ErrorAction SilentlyContinue |
          Select-Object -First 1 | ForEach-Object { Split-Path (Split-Path $_.FullName -Parent) -Parent }
  if (-not $root) { throw "could not find the payload in the downloaded zip" }
} else {
  $root = $PSScriptRoot
}
Say "source: $root"

# ---------- 2. python ----------
$pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pyExe) {
  foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                   "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                   "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe")) {
    if (Test-Path $c) { $pyExe = $c; break }
  }
}
if (-not $pyExe) {
  Write-Host "  ! Python 3 not found." -ForegroundColor Yellow
  Write-Host "    install it from https://python.org (tick 'Add python to PATH'), then re-run this." -ForegroundColor Yellow
  return
}
Say "python: $pyExe"
Say "installing python packages (requests, pillow)..."
& $pyExe -m pip install --quiet --disable-pip-version-check requests pillow

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

# ---------- 6. start ----------
$pa = Join-Path $Dir 'pa.py'
if (Test-Path $pa) { & $pyExe $pa start }

Write-Host ""
Write-Host "  DONE" -ForegroundColor Green
Say "drop photos into  : $Dir\INPUT"
Say "collect finished  : $Dir\FINAL"
Say "control panel     : double-click 'Passport Auto TUI.cmd'"
Say "windows shortcuts : '1 - Drop Photo Here' / '2 - Get Finished Photos' / '3 - Status'"
Write-Host ""
