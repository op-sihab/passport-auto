<#
  Create every shortcut Passport Auto needs: desktop launchers + autostart at login.
  Paths are derived from this script's own location, so it works on any machine.
#>
$ErrorActionPreference = 'Stop'

$base = $PSScriptRoot
$ico  = Join-Path $base 'passport_auto.ico'
$cmd  = "$env:SystemRoot\System32\cmd.exe"

# find python
$pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pyExe) {
  foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
                   "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                   "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                   "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe")) {
    if (Test-Path $c) { $pyExe = $c; break }
  }
}
if (-not $pyExe) { throw "python not found - install Python 3 first" }
$pyw = Join-Path (Split-Path $pyExe -Parent) 'pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = $pyExe }

function New-Lnk($path, $exe, $argline, $desc) {
  $w = New-Object -ComObject WScript.Shell
  $s = $w.CreateShortcut($path)
  $s.TargetPath = $exe
  $s.Arguments = $argline
  $s.WorkingDirectory = $base
  $s.IconLocation = "$ico,0"
  $s.Description = $desc
  $s.Save()
  Write-Output "  $path"
}

# every desktop this user actually sees (some machines redirect Desktop to OneDrive)
$desktops = @()
foreach ($d in @([Environment]::GetFolderPath('Desktop'),
                 (Join-Path $env:USERPROFILE 'Desktop'),
                 (Join-Path $env:USERPROFILE 'OneDrive\Desktop'))) {
  if ($d -and (Test-Path $d) -and ($desktops -notcontains $d)) { $desktops += $d }
}

$pa = Join-Path $base 'pa.py'
$tui = Join-Path $base 'Passport Auto TUI.cmd'

Write-Output "Desktop shortcuts:"
foreach ($d in $desktops) {
  # clear older names from previous layouts
  foreach ($old in @('Passport Auto.lnk','Passport Auto - Folder.lnk',
                     'Passport Auto - Stop.lnk','Passport Auto - Status.lnk',
                     'Passport Auto - Output Folder.lnk')) {
    $p = Join-Path $d $old
    if (Test-Path $p) { Remove-Item $p -Force }
  }
  New-Lnk (Join-Path $d '0 - Control Panel (TUI).lnk') $cmd "/k `"$tui`""            'Passport Auto menu'
  New-Lnk (Join-Path $d '1 - Drop Photo Here.lnk')      'explorer.exe' "`"$base\INPUT`"" 'Put raw photos in this folder'
  New-Lnk (Join-Path $d '2 - Get Finished Photos.lnk')  'explorer.exe' "`"$base\FINAL`"" 'Finished passport photos'
  New-Lnk (Join-Path $d '3 - Status.lnk')               $cmd "/k `"$pyExe`" `"$pa`" status" 'Is Passport Auto running?'
  New-Lnk (Join-Path $d 'Passport Auto - On.lnk')       $pyw "`"$pa`" start"          'Start automatic processing'
  New-Lnk (Join-Path $d 'Passport Auto - Off.lnk')      $pyw "`"$pa`" stop"           'Stop automatic processing'
}

# ---------- autostart at login ----------
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
if (Test-Path $startup) {
  Write-Output "Startup:"
  New-Lnk (Join-Path $startup 'Passport Auto.lnk') $pyw "`"$pa`" start" 'Start Passport Auto watcher'
}
