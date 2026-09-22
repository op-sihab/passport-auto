<#
  Register Passport Auto's own AppUserModelID so Windows toasts show OUR name and
  icon instead of "Windows PowerShell". Windows resolves both from the Start Menu
  shortcut that carries the AUMID, so we create one and stamp it.
#>
$ErrorActionPreference = 'Stop'

$AUMID = 'NousResearch.PassportAuto.Pipeline'
$base  = $PSScriptRoot
$ico   = Join-Path $base 'passport_auto.ico'
$lnk   = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Passport Auto.lnk'

$pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pyExe) {
  foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                   "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                   "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe")) {
    if (Test-Path $c) { $pyExe = $c; break }
  }
}
$pyw = if ($pyExe) { Join-Path (Split-Path $pyExe -Parent) 'pythonw.exe' } else { 'pythonw.exe' }
if (-not (Test-Path $pyw)) { $pyw = $pyExe }

# ---------- 1. the Start Menu shortcut ----------
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($lnk)
$s.TargetPath       = $pyw
$s.Arguments        = '"' + (Join-Path $base 'pa.py') + '" start'
$s.WorkingDirectory = $base
$s.IconLocation     = "$ico,0"
$s.Description      = 'Passport Auto pipeline'
$s.Save()
Write-Output "shortcut: $lnk"

# ---------- 2. stamp the AppUserModelID onto it ----------
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class Aumid {
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct PROPERTYKEY { public Guid fmtid; public uint pid; }

    [StructLayout(LayoutKind.Explicit)]
    public struct PROPVARIANT {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(8)] public IntPtr ptr;
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    public class ShellLink { }

    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPersistFile {
        void GetClassID(out Guid pClassID);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, bool fRemember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
        void GetCurFile(out IntPtr ppszFileName);
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyStore {
        uint GetCount();
        PROPERTYKEY GetAt(uint iProp);
        void GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
        void SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);
        void Commit();
    }

    public static void Set(string lnkPath, string aumid) {
        var link = (IPropertyStore)(object)new ShellLink();
        var pf = (IPersistFile)link;
        pf.Load(lnkPath, 2);

        PROPERTYKEY key = new PROPERTYKEY();
        key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
        key.pid = 5;

        PROPVARIANT pv = new PROPVARIANT();
        pv.vt = 31;
        pv.ptr = Marshal.StringToCoTaskMemUni(aumid);
        try {
            link.SetValue(ref key, ref pv);
            link.Commit();
            pf.Save(lnkPath, true);
        } finally {
            Marshal.FreeCoTaskMem(pv.ptr);
        }
    }
}
"@

[Aumid]::Set($lnk, $AUMID)
Write-Output "aumid set: $AUMID"
