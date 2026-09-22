#!/usr/bin/env python
"""pa.py — command-line control for the Passport Auto pipeline.

Usage:
  pa.py start                 start the folder watcher in the background
  pa.py stop                  stop the watcher
  pa.py restart               stop + start
  pa.py status                running? queue counts, last processed
  pa.py process <file>        run one image through the pipeline now
  pa.py queue                 list files waiting in INPUT
  pa.py set-input <folder>    watch a different folder (camera, Downloads, ...)
  pa.py settings              show current settings
  pa.py log [-n N]            tail the error log
  pa.py notify [-n N]         tail the notification history
  pa.py test-notify           send a test toast
"""
import os
import subprocess
import sys
import time
import json

BASE = os.path.join(os.path.expanduser("~"), "Desktop", "Passport Auto")
SETTINGS = os.path.join(BASE, "settings.json")


def load_settings():
    d = {"input_folder": os.path.join(BASE, "INPUT"), "workers": 3}
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            d.update(loaded)
    except Exception:
        pass
    return d


def save_settings(d):
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


SETTINGS_D = load_settings()
DIRS = {k: os.path.join(BASE, v) for k, v in {
    "INPUT": "INPUT", "CROPPED": "CROPPED", "FINAL": "FINAL",
    "DONE": "DONE", "FAILED": "FAILED"}.items()}
if SETTINGS_D.get("input_folder"):
    DIRS["INPUT"] = os.path.abspath(os.path.expanduser(str(SETTINGS_D["input_folder"])))
PID_FILE = os.path.join(BASE, "watcher.pid")
STATE_FILE = os.path.join(BASE, "state.json")
WATCHER = os.path.join(BASE, "pipeline_watcher.py")
WATCHER_LOG = os.path.join(BASE, "watcher.log")
NOTIFY_LOG = os.path.join(BASE, "notifications.log")
PY = sys.executable
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _run_quiet(args):
    """Run a helper command without flashing a console window."""
    return subprocess.run(args, capture_output=True, text=True,
                          creationflags=_NO_WINDOW)


def _running():
    if not os.path.exists(PID_FILE):
        return None
    try:
        pid = int(open(PID_FILE).read().strip())
    except Exception:
        return None
    out = _run_quiet(["tasklist", "/FI", f"PID eq {pid}", "/NH"]).stdout
    return pid if str(pid) in out else None


def cmd_start():
    pid = _running()
    if pid:
        print(f"already running (pid {pid})")
        return 0
    os.makedirs(BASE, exist_ok=True)
    logf = open(WATCHER_LOG, "a", encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
    p = subprocess.Popen([PY, "-u", WATCHER], stdout=logf, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=flags, cwd=BASE)
    time.sleep(1.5)
    if p.poll() is not None:
        print("watcher failed to start — see watcher.log")
        return 1
    open(PID_FILE, "w").write(str(p.pid))
    print(f"watcher started (pid {p.pid})")
    print(f"  drop images into: {DIRS['INPUT']}")
    return 0


def cmd_stop():
    pid = _running()
    if not pid:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        print("not running")
        return 0
    subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                   capture_output=True, text=True, creationflags=_NO_WINDOW)
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    print(f"stopped (pid {pid})")
    return 0


def cmd_status():
    pid = _running()
    print("watcher : " + (f"RUNNING (pid {pid})" if pid else "stopped"))
    print(f"folder  : {BASE}")
    print(f"watching: {DIRS['INPUT']}")
    print(f"workers : {SETTINGS_D.get('workers', 3)}")
    print("-" * 46)
    for k, d in DIRS.items():
        try:
            n = len([f for f in os.listdir(d) if f.lower().endswith(IMG_EXT)])
        except Exception:
            n = 0
        print(f"  {k:<8} {n:>4} image(s)")
    if os.path.exists(STATE_FILE):
        try:
            st = json.load(open(STATE_FILE, encoding="utf-8"))
            print("-" * 46)
            print(f"last event : {st.get('event','?')}  {st.get('name','')}  {st.get('detail','')}")
            print(f"updated    : {st.get('time','?')}")
            print(f"processed  : {st.get('count', 0)} this session")
        except Exception:
            pass
    return 0


def cmd_queue():
    try:
        files = sorted(f for f in os.listdir(DIRS["INPUT"]) if f.lower().endswith(IMG_EXT))
    except Exception as e:
        print("cannot list INPUT:", e)
        return 1
    if not files:
        print("queue empty")
        return 0
    for f in files:
        print(" ", f)
    print(f"({len(files)} waiting)")
    return 0


def cmd_process(path):
    if not os.path.exists(path):
        print("no such file:", path)
        return 1
    sys.path.insert(0, BASE)
    import pipeline_watcher as pw
    pw.process(path)
    return 0


def _tail(path, n):
    if not os.path.exists(path):
        print(f"(no {os.path.basename(path)} yet)")
        return
    lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    for line in lines[-n:]:
        print(line)


def cmd_set_input(path):
    """Point the watch folder somewhere else (camera folder, Downloads, ...)."""
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(p):
        try:
            os.makedirs(p, exist_ok=True)
        except Exception as e:
            print(f"cannot create folder: {e}")
            return 1
    SETTINGS_D["input_folder"] = p
    save_settings(SETTINGS_D)
    DIRS["INPUT"] = p
    print(f"watch folder set to:\n  {p}")
    was = _running()
    if was:
        print("restarting watcher to apply...")
        cmd_stop()
        time.sleep(1)
        cmd_start()
    else:
        print("start the watcher for it to take effect:  pa.py start")
    return 0


def cmd_settings_cmd():
    print(f"settings file: {SETTINGS}")
    for k, v in SETTINGS_D.items():
        print(f"  {k:<14} {v}")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1].lower()
    rest = sys.argv[2:]
    n = 20
    if "-n" in rest:
        i = rest.index("-n")
        n = int(rest[i + 1])
        rest = rest[:i] + rest[i + 2:]

    if cmd == "start":
        return cmd_start()
    if cmd == "stop":
        return cmd_stop()
    if cmd == "restart":
        cmd_stop(); time.sleep(1); return cmd_start()
    if cmd == "status":
        return cmd_status()
    if cmd == "queue":
        return cmd_queue()
    if cmd in ("set-input", "setinput"):
        if not rest:
            print("usage: pa.py set-input <folder path>")
            return 1
        return cmd_set_input(rest[0])
    if cmd in ("settings", "config"):
        return cmd_settings_cmd()
    if cmd == "process":
        if not rest:
            print("usage: pa.py process <file>")
            return 1
        return cmd_process(rest[0])
    if cmd == "log":
        _tail(os.path.join(BASE, "error.log"), n)
        return 0
    if cmd == "watcher-log":
        _tail(WATCHER_LOG, n)
        return 0
    if cmd == "notify":
        _tail(NOTIFY_LOG, n)
        return 0
    if cmd in ("test-notify", "notify-test"):
        sys.path.insert(0, BASE)
        import pauto_notify
        ok = pauto_notify.notify("Passport Auto", "Test notification — all wired up.")
        print("toast sent:", ok)
        return 0
    print("unknown command:", cmd)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
