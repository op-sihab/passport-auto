#!/usr/bin/env python
"""pa_tui.py - simple menu for Passport Auto. No dependencies, runs in cmd/PowerShell.

    double-click  Passport Auto TUI.cmd   (or run: python pa_tui.py)
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PA = os.path.join(BASE, "pa.py")
sys.path.insert(0, BASE)

# enable ANSI colours on Windows consoles
if os.name == "nt":
    os.system("")

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "blue": "\033[38;5;39m", "green": "\033[38;5;42m", "red": "\033[38;5;203m",
    "yellow": "\033[38;5;221m", "grey": "\033[38;5;245m",
}


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def load():
    import json
    p = os.path.join(BASE, "settings.json")
    d = {"input_folder": os.path.join(BASE, "INPUT"), "workers": 3}
    try:
        with open(p, encoding="utf-8") as f:
            d.update(json.load(f))
    except Exception:
        pass
    return d


def count_images(folder):
    try:
        return len([f for f in os.listdir(folder)
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))])
    except Exception:
        return 0


def run_pa(*args):
    """Call pa.py in-process-ish and return its output."""
    r = subprocess.run([PY, PA, *args], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (r.stdout or "") + (r.stderr or "")


def is_running():
    out = run_pa("status")
    return "RUNNING" in out


def banner():
    s = load()
    running = is_running()
    state = f"{C['green']}RUNNING{C['reset']}" if running else f"{C['red']}STOPPED{C['reset']}"
    print(f"{C['blue']}{C['bold']}  PASSPORT AUTO{C['reset']}   {state}")
    print(f"{C['grey']}  watch : {s['input_folder']}{C['reset']}")
    print(f"{C['grey']}  queue : {count_images(s['input_folder'])} waiting"
          f"   done : {count_images(os.path.join(BASE,'FINAL'))} finished{C['reset']}")
    if not keys_present():
        print(f"{C['yellow']}  ! API keys are not set - press k to enter them{C['reset']}")
    print()


def keys_present():
    import json
    try:
        with open(os.path.join(BASE, "secrets.json"), encoding="utf-8") as f:
            d = json.load(f)
        return all(v.strip() and "your_" not in v
                   for v in (d.get("fireworks_api_key", ""), d.get("cun_api_key", "")))
    except Exception:
        return False


MENU = [
    ("1", "Start processing", "start"),
    ("2", "Stop processing", "stop"),
    ("3", "Refresh status", None),
    ("4", "Open DROP folder (put photos here)", "open_input"),
    ("5", "Open FINISHED folder (get photos here)", "open_final"),
    ("6", "Change watch folder", "set_input"),
    ("7", "Test notification", "test_notify"),
    ("8", "Recent activity", "log"),
    ("9", "Advanced settings", "settings"),
    ("k", "Enter API keys", "setup"),
    ("0", "Exit", "exit"),
]


def draw_menu():
    for key, label, _ in MENU:
        colour = C["red"] if key == "0" else C["reset"]
        print(f"   {C['bold']}{key}{C['reset']}  {colour}{label}{C['reset']}")
    print()


def pause(msg="  Press Enter to continue..."):
    try:
        input(f"{C['grey']}{msg}{C['reset']}")
    except (EOFError, KeyboardInterrupt):
        pass


def do(action):
    if action == "start":
        print(run_pa("start"))
        pause()
    elif action == "stop":
        print(run_pa("stop"))
        pause()
    elif action == "open_input":
        subprocess.Popen(["explorer.exe", load()["input_folder"]])
        pause("  Folder opened. Press Enter...")
    elif action == "open_final":
        subprocess.Popen(["explorer.exe", os.path.join(BASE, "FINAL")])
        pause("  Folder opened. Press Enter...")
    elif action == "set_input":
        print(f"{C['grey']}  current: {load()['input_folder']}{C['reset']}")
        try:
            p = input("  New folder path (Enter to cancel): ").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            return
        if p:
            print(run_pa("set-input", p))
            pause()
    elif action == "test_notify":
        sys.path.insert(0, BASE)
        import pauto_notify
        ok = pauto_notify.notify("Passport Auto", "Test notification - all good.")
        print(f"  toast sent: {ok}")
        pause()
    elif action == "log":
        print(run_pa("notify", "-n", "12"))
        pause()
    elif action == "setup":
        # interactive prompt - run it as its own process so input() works normally
        subprocess.run([PY, PA, "setup"])
        pause()
    elif action == "settings":
        print(run_pa("settings"))
        try:
            w = input("  Workers (Enter to keep): ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if w.isdigit() and int(w) > 0:
            import json
            d = load()
            d["workers"] = int(w)
            with open(os.path.join(BASE, "settings.json"), "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            print("  saved. restart (2 then 1) to apply.")
            pause()


def main():
    while True:
        clear()
        banner()
        draw_menu()
        try:
            choice = input(f"{C['bold']}  choose > {C['reset']}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        act = dict((k, a) for k, _, a in MENU).get(choice)
        if act == "exit":
            return 0
        if choice not in dict((k, k) for k, _, _ in MENU):
            continue
        if act:
            do(act)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(0)
