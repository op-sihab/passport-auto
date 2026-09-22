$files = @(
  'E:\passport-auto-repo\install.ps1',
  'E:\passport-auto-repo\scripts\make_shortcuts.ps1',
  'E:\passport-auto-repo\scripts\register_appid.ps1'
)
foreach ($f in $files) {
  $errs = $null
  [System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$errs) | Out-Null
  if ($errs -and $errs.Count -gt 0) {
    Write-Output ("ERR  " + (Split-Path $f -Leaf))
    $errs | ForEach-Object { Write-Output ("       " + $_.Message) }
  } else {
    Write-Output ("OK   " + (Split-Path $f -Leaf))
  }
}
