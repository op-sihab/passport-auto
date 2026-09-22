"""Windows toast notifications for the Passport Auto pipeline.

No pip deps — drives the built-in WinRT toast API through PowerShell.
Every call is best-effort: a notification failure must never break the pipeline.
"""
import os
import subprocess
import sys
import time

# our own AppUserModelID - registered by register_appid.ps1 via a Start Menu
# shortcut that carries our icon. Using PowerShell's AUMID made Windows show
# the PowerShell icon instead of ours.
_APPID = "NousResearch.PassportAuto.Pipeline"

_PS = r"""
param([string]$Title, [string]$Msg)
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $tpl.GetElementsByTagName('text')
$texts.Item(0).AppendChild($tpl.CreateTextNode($Title)) | Out-Null
$texts.Item(1).AppendChild($tpl.CreateTextNode($Msg)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:PA_TOAST_APPID).Show($toast)
"""


_PS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "toast.ps1")
_LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon", "icon_256.png")

# hide the PowerShell console — otherwise a black window flashes on every toast
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def notify(title: str, msg: str, sound: bool = True) -> bool:
    """Show a Windows toast with the Passport Auto icon. Never raises."""
    try:
        env = dict(os.environ, PA_TOAST_APPID=_APPID)
        args = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", _PS_FILE, "-Title", title, "-Msg", msg]
        if os.path.exists(_LOGO):
            args += ["-Logo", _LOGO]
        p = subprocess.run(args, capture_output=True, timeout=20, env=env,
                           creationflags=_NO_WINDOW)
        if p.returncode != 0:
            try:
                sys.stderr.write((p.stderr or b"").decode("utf-8", "ignore")[:300] + "\n")
            except Exception:
                pass
        return p.returncode == 0
    except Exception:
        return False


def beep(freq: int = 880, dur: int = 200):
    """Fallback audible cue (works even if toasts are disabled)."""
    try:
        import winsound
        winsound.Beep(freq, dur)
    except Exception:
        pass


def event(kind: str, name: str, extra: str = "", beeps: bool = True):
    """kind: detect | done | fail"""
    titles = {
        "detect": "\U0001F4F7 New image detected",
        "done": "\u2705 Passport photo ready",
        "fail": "\u26A0\uFE0F Processing failed",
    }
    title = titles.get(kind, "Passport Auto")
    msg = f"{name} {extra}".strip()
    if beeps:
        if kind == "done":
            beep(1000, 120)
        elif kind == "fail":
            beep(400, 350)
        else:
            beep(700, 90)
    notify(title, msg)
    _append_hist(kind, name, extra)


def _hist_path() -> str:
    base = os.path.join(os.path.expanduser("~"), "Desktop", "Passport Auto")
    return os.path.join(base, "notifications.log")


def _append_hist(kind: str, name: str, extra: str):
    try:
        with open(_hist_path(), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {kind}\t{name}\t{extra}\n")
    except Exception:
        pass


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "test":
        ok = notify("Passport Auto", "Notification test \u2014 everything is wired up.")
        print("toast sent:", ok)
        beep(1000, 150)
    elif len(args) >= 2:
        event(args[0], args[1], " ".join(args[2:]))
        print("event sent:", args[0], args[1])
    else:
        print("usage: pauto_notify.py test | <detect|done|fail> <name> [extra]")
