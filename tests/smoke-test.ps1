# Sandbox test: replicate install.ps1's fetch + flatten steps only.
# Does NOT touch shortcuts, the AUMID registration or the running watcher.
$ErrorActionPreference = 'Stop'
$REPO_ZIP = 'https://github.com/op-sihab/passport-auto/archive/refs/heads/main.zip'
$Dir = Join-Path $env:TEMP 'pa_installtest'

if (Test-Path $Dir) { Remove-Item $Dir -Recurse -Force }
New-Item -ItemType Directory -Path $Dir -Force | Out-Null

$tmp = Join-Path $env:TEMP ("pa_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
Write-Output "1. downloading..."
$pkg = Join-Path $tmp "pkg.zip"
Invoke-WebRequest -Uri $REPO_ZIP -OutFile $pkg -UseBasicParsing
Write-Output ("   got " + [math]::Round((Get-Item $pkg).Length/1KB,1) + " KB")

Write-Output "2. extracting..."
Expand-Archive -Path $pkg -DestinationPath $tmp -Force

$found = Get-ChildItem $tmp -Recurse -Filter 'pipeline_watcher.py' -ErrorAction SilentlyContinue |
         Select-Object -First 1
if (-not $found) { throw "no sources found in the archive" }
$root = Split-Path (Split-Path $found.FullName -Parent) -Parent
Write-Output "   root = $root"

Write-Output "3. flattening..."
foreach ($sub in @('src','scripts','assets','launchers')) {
  $p = Join-Path $root $sub
  if (Test-Path $p) { Copy-Item (Join-Path $p '*') $Dir -Recurse -Force }
}
foreach ($d in @('INPUT','CROPPED','FINAL','DONE','FAILED')) {
  New-Item -ItemType Directory -Path (Join-Path $Dir $d) -Force | Out-Null
}
Copy-Item (Join-Path $root 'config\settings.example.json') (Join-Path $Dir 'settings.json') -Force
Copy-Item (Join-Path $root 'config\secrets.example.json')  (Join-Path $Dir 'secrets.json')  -Force

Write-Output ""
Write-Output "4. result:"
Get-ChildItem $Dir | ForEach-Object {
  if ($_.PSIsContainer) { Write-Output ("   [dir] " + $_.Name) }
  else { Write-Output ("         " + $_.Name) }
}

Write-Output ""
Write-Output "5. can the CLI run from this layout?"
$py = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
& $py (Join-Path $Dir 'pa.py') settings
Remove-Item $Dir -Recurse -Force
Remove-Item $tmp -Recurse -Force
Write-Output "   (sandbox cleaned up)"
