# Passport Auto

Windows folder-watcher that turns any photo dropped into a folder into a
passport-ready studio photo — AI crop, azure-blue studio background, 4:5 output —
with desktop notifications. Zero-touch once installed: it starts with Windows and
runs in the background.

```
photo  ->  INPUT/  ->  [ AI crop ]  ->  [ studio edit ]  ->  FINAL/
```

## Install

One line in PowerShell:

```powershell
iex (irm https://raw.githubusercontent.com/op-sihab/passport-auto/main/install.ps1)
```

The installer copies the program, installs its Python dependencies, creates the
desktop shortcuts, registers the notification icon and starts the watcher.

From a downloaded zip:

```powershell
iex "& { $(irm https://raw.githubusercontent.com/op-sihab/passport-auto/main/install.ps1) } -Zip https://<host>/passport-auto.zip"
```

From a local checkout:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

## After installing

The installer asks for your two API keys straight away and stores them in
`secrets.json` (git-ignored). You can change them at any time:

```
pa setup      enter or replace the keys (interactive)
pa keys       show the keys stored on this machine
```

`secrets.json` looks like this:

```json
{
  "fireworks_api_key": "fw_...",
  "cun_api_key": "sk-..."
}
```

| Key | Used for | Where to get it |
|---|---|---|
| `fireworks_api_key` | analyses each photo and picks the crop | fireworks.ai → API Keys |
| `cun_api_key` | redraws the background in studio blue | cun.ai → API keys |

Both are billed per use, so keep them private.

## Using it

| Folder | Purpose |
|---|---|
| `INPUT/` | drop raw photos here |
| `FINAL/` | finished passport photos — collect them here |
| `CROPPED/` | intermediate cropped images |
| `DONE/` | source photos that were processed |
| `FAILED/` | anything that errored (see `error.log`) |

Or just use the desktop shortcuts:

| Shortcut | Does |
|---|---|
| `0 - Control Panel (TUI)` | interactive menu |
| `1 - Drop Photo Here` | opens `INPUT` |
| `2 - Get Finished Photos` | opens `FINAL` |
| `3 - Status` | shows whether it is running |
| `Passport Auto - On / Off` | start / stop processing |

## Control panel (TUI)

Double-click **Passport Auto TUI.cmd**, or run `python pa_tui.py`:

```
  PASSPORT AUTO   RUNNING
  watch : ...\Passport Auto\INPUT
  queue : 0 waiting   done : 39 finished

   1  Start processing        5  Open FINISHED folder
   2  Stop processing         6  Change watch folder
   3  Refresh status          7  Send test notification
   4  Open DROP folder        8  Recent activity
                              9  Advanced settings
   0  Exit
```

## CLI

```
pa start | stop | restart | status | queue
pa process <file>          run one photo now
pa set-input <folder>      watch a different folder
pa settings                show current settings
pa setup                   enter your API keys (interactive)
pa keys                    show the keys stored on this machine
pa log | notify            tail the error log / notification history
pa test-notify             send a test toast
```

## Configuration

`settings.json` (created on install):

| Key | Default | Meaning |
|---|---|---|
| `input_folder` | `INPUT` | folder to watch — point it anywhere |
| `workers` | `3` | how many photos are processed in parallel |
| `keep_original` | `false` | copy instead of move the source (needed for synced folders) |
| `process_existing` | `false` | also process photos already in the folder on first start |

> Leave `process_existing` off when pointing at an existing photo library: each
> photo costs an API call, and the whole backlog would be processed.

## How it works

1. **Crop** — GLM (`glm-5p3-flash`) is shown the full-size photo and returns a
   framing box: head 50–55% of the frame, 6–8% headroom, cut just under the
   collar, exact 4:5.
2. **Edit** — the crop goes to `gpt-image-2.5-sunburst`, which repaints the
   background azure (`#4A9FF5`) while preserving the face.
3. **Size lock** — the result is resized back to the exact crop size so framing
   never drifts.
4. Both steps retry up to 3 times; the APIs occasionally return an empty body.

Three workers run in parallel, so a batch takes roughly as long as one photo.

## Repository layout

```
src/        pipeline_watcher.py, pa.py (CLI), pa_tui.py, pauto_notify.py
scripts/    make_shortcuts.ps1, register_appid.ps1, toast.ps1, render_icon.py
assets/     icon.svg, icon.ico, icon/*.png
launchers/  pa.cmd, Passport Auto TUI.cmd, _find_python.cmd
config/     settings.example.json, secrets.example.json
docs/       USAGE.bn.txt (Bengali guide)
install.ps1 one-line installer
```

The installer flattens `src/`, `scripts/`, `assets/` and `launchers/` into a
single working folder, because the programs reference each other by name.

## Requirements

- Windows 10 or 11

That is all. If Python is missing the installer adds it for you (via winget,
falling back to the official python.org installer), then installs the
`requests` and `pillow` packages itself.

## Licence

MIT
