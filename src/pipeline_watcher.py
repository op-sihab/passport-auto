#!/usr/bin/env python3
"""
pipeline_watcher.py — Desktop Folder Auto Pipeline (Camera -> Final Passport Photo)

Workflow:
  1. Drop RAW camera images into  Desktop/Passport Auto/INPUT/
  2. STEP 1 (AI CROP):  merge.dev GLM-5.3-flash analyzes -> 40x50mm 4:5 studio crop -> CROPPED/
  3. STEP 2 (EDIT):     cropped image auto-uploaded to Gemini (headless CDP bot)
                        with fixed prompt: HD enhance + sky-blue background, no other changes
  4. STEP 3 (FINAL):    Gemini's edited image extracted -> FINAL/<name>_final.jpg
  5. Raw original moved to DONE/ (or FAILED/ on error, with reason in error.log)

Run:  python pipeline_watcher.py     (keeps watching; Ctrl+C to stop)
"""
import os
import sys
import time
import json
import re
import queue
import base64
import io
import shutil
import threading
import requests
from PIL import Image

# --- locate gemini_bot engine (same folder as this script's sibling) ---
HOME = os.path.expanduser("~")
GEMINI_DIR = HOME  # C:/Users/scptb/gemini_bot.py
sys.path.insert(0, GEMINI_DIR)

# the working folder is wherever this file lives, so the program runs correctly
# no matter which folder it was installed into
BASE = os.path.dirname(os.path.abspath(__file__))
DIR_INPUT = os.path.join(BASE, "INPUT")
DIR_CROP = os.path.join(BASE, "CROPPED")
DIR_FINAL = os.path.join(BASE, "FINAL")
DIR_DONE = os.path.join(BASE, "DONE")
DIR_FAIL = os.path.join(BASE, "FAILED")
LOG = os.path.join(BASE, "error.log")

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff")

# phone photos are usually HEIC — teach Pillow to open them
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

# ---------------- user settings (settings.json) ----------------
SETTINGS = os.path.join(BASE, "settings.json")


def load_settings():
    """User-editable settings. A missing file just means defaults."""
    d = {"input_folder": DIR_INPUT, "workers": 3}
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                if v not in (None, "", []):   # blank means "use the default"
                    d[k] = v
    except Exception:
        pass
    return d


def save_settings(d):
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


_SETTINGS = load_settings()

# the watch folder can be pointed anywhere (camera folder, Downloads, a network
# drive, ...) by editing settings.json or running:  pa.py set-input <path>
if _SETTINGS.get("input_folder"):
    DIR_INPUT = os.path.abspath(os.path.expanduser(str(_SETTINGS["input_folder"])))

# ---------------- processed ledger (needed when keep_original is on) ----------------
# With keep_original the source file stays in the watch folder forever, so we
# remember what has already been handled; otherwise every restart would re-run
# the whole library through the paid API.
LEDGER = os.path.join(BASE, "processed.txt")
_LEDGER_LOCK = threading.Lock()


def load_ledger():
    try:
        with open(LEDGER, encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()}
    except Exception:
        return set()


def add_ledger(name):
    with _LEDGER_LOCK:
        try:
            with open(LEDGER, "a", encoding="utf-8") as f:
                f.write(name + "\n")
        except Exception:
            pass

# ---------------- secrets (never commit these) ----------------
SECRETS = os.path.join(BASE, "secrets.json")


def secret(name, default=""):
    """Read a key from secrets.json, falling back to an environment variable."""
    try:
        with open(SECRETS, encoding="utf-8") as f:
            v = json.load(f).get(name)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(name.upper(), default)


# ---------------- STEP 1: AI crop via Fireworks GLM ----------------
FW_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
FW_KEY = secret("fireworks_api_key")
FW_MODEL = "accounts/fireworks/models/glm-5p3-flash"


def log_err(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


# ---------------- notifications + shared state (CLI reads state.json) ----------------
try:
    import pauto_notify
except Exception:  # notifications must never block the pipeline
    pauto_notify = None

STATE = os.path.join(BASE, "state.json")
_SESSION = {"count": 0}
_STATE_LOCK = threading.Lock()


def _state(event: str, name: str = "", detail: str = ""):
    with _STATE_LOCK:
        if event == "done":
            _SESSION["count"] += 1
        try:
            tmp = STATE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"event": event, "name": name, "detail": detail,
                           "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "count": _SESSION["count"]}, f)
            os.replace(tmp, STATE)
        except Exception:
            pass


def _notify(kind: str, name: str, detail: str = ""):
    _state(kind if kind != "detect" else "detect", name, detail)
    if pauto_notify:
        try:
            pauto_notify.event(kind, name, detail)
        except Exception:
            pass


def ai_crop_box(img: Image.Image):
    """Ask Fireworks GLM-5.3-flash for the best spacious studio crop box. Returns (x0,y0,x1,y1)."""
    orig_w, orig_h = img.size
    preview = img.copy()
    if preview.mode in ("RGBA", "P"):
        preview = preview.convert("RGB")
    pw, ph = preview.size
    sx, sy = 1.0, 1.0  # no downscale — AI sees full-size image

    buf = io.BytesIO()
    preview.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = f"""You are a high-end commercial photo studio specialist creating a relaxed, spacious, premium studio portrait (40x50mm, 4:5 aspect ratio).
Image size: width={pw}, height={ph}.

CRITICAL FRAMING RULES (PASSPORT STANDARD — head close, collar visible, minimal jama):
1. Head size rule: Head height (top of hair/crown/HEADWEAR to bottom of chin) MUST occupy 50% to 55% of the total crop height (NEVER tight 70-80%, NEVER let headwear touch the top edge).
2. Headroom rule: Leave a slim, clean 6% to 8% headroom above the crown/hair/HEADWEAR (small blue gap, close to the head).
3. Torso/Chest rule: The bottom edge MUST cut just under the shirt collar / first button, showing the SHOULDERS and a modest bit of chest/collar — chin + ~14-16% of frame height. A little garment is fine as long as it's only around the collar/shoulders, NEVER a long jama body or wide drape.
4. Clean background: Completely exclude any unwanted background stickers, QR codes or artifacts.
5. Centering: Center horizontally on the facial midline (bridge of nose).
6. Exact 4:5 aspect ratio: crop_width = crop_height * 0.8.

Return ONLY a JSON object (no markdown, no other text) in the {pw}x{ph} coordinate system:
{{"crop_x_min": <int>, "crop_y_min": <int>, "crop_x_max": <int>, "crop_y_max": <int>}}
"""
    payload = {
        "model": FW_MODEL,
        "max_tokens": 2048,
        "reasoning_effort": "low",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}]
    }
    last_err = ""
    c = None
    for attempt in range(3):
        try:
            r = requests.post(FW_URL, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {FW_KEY}"
            }, json=payload, timeout=90)
            if r.status_code != 200:
                last_err = f"fireworks HTTP {r.status_code}: {r.text[:200]}"
            else:
                text = r.json()["choices"][0]["message"]["content"]
                m = re.search(r"\{[\s\S]*?\}", text)
                if not m:
                    last_err = f"No JSON in AI reply: {text[:200]}"
                else:
                    c = json.loads(m.group(0))
                    break
        except Exception as e:
            last_err = f"{e.__class__.__name__}: {e}"
        print(f"    [CROP] attempt {attempt+1} failed ({last_err[:70]}) -> retrying",
              flush=True)
        if attempt < 2:
            time.sleep(2)
    if c is None:
        raise RuntimeError(f"crop failed after 3 attempts: {last_err}")

    x0 = int(round(c["crop_x_min"] * sx)); y0 = int(round(c["crop_y_min"] * sy))
    x1 = int(round(c["crop_x_max"] * sx)); y1 = int(round(c["crop_y_max"] * sy))

    # snap to 4:5, clamp inside image
    ch = y1 - y0
    cw = int(round(ch * 0.8))
    cx = (x0 + x1) // 2
    x0 = max(0, cx - cw // 2)
    x1 = min(orig_w, x0 + cw)
    if x1 - x0 < cw:
        x0 = max(0, x1 - cw)
    y0 = max(0, y0)
    y1 = min(orig_h, y0 + ch)

    # GUARDRAIL: enforce minimum 5% headroom — AI sometimes returns tight boxes.
    # Detect real head_top on the ORIGINAL via bg-mask in middle columns.
    try:
        import numpy as _np
        _arr = _np.array(img)
        # normalise to 3 channels — RGBA/LA/grayscale input otherwise breaks the
        # reshape below ("cannot reshape array of size N into shape (3)")
        if _arr.ndim == 2:
            _arr = _np.stack([_arr] * 3, axis=-1)
        elif _arr.ndim == 3 and _arr.shape[2] > 3:
            _arr = _arr[:, :, :3]
        elif _arr.ndim == 3 and _arr.shape[2] == 1:
            _arr = _np.repeat(_arr, 3, axis=2)
        _h, _w = _arr.shape[:2]
        _corners = _np.concatenate([_arr[:50, :50].reshape(-1, 3), _arr[:50, -50:].reshape(-1, 3),
                                    _arr[-50:, :50].reshape(-1, 3), _arr[-50:, -50:].reshape(-1, 3)])
        _bg = _corners.mean(axis=0)
        _diff = _np.sqrt(((_arr.astype(float) - _bg) ** 2).sum(axis=2))
        _mask = _diff > 45
        _mid = _mask[:, _w // 4: 3 * _w // 4]
        _rowsum = _mid.sum(axis=1)
        _head_top = next((y for y in range(_h) if _rowsum[y] >= 10), 0)
        _ch = y1 - y0
        _have = (y0 - _head_top) / _ch if _ch else 0
        if _have < 0.05:
            # expand upward so headroom becomes 7% of new height, keep bottom (chest):
            # H' = (y1-ht)/1.07  =>  (y0'-ht)/H' = 0.07
            _new_h = int(round((y1 - _head_top) / 1.07))
            y0 = max(0, y1 - _new_h)
            _ch2 = y1 - y0
            _cw2 = int(round(_ch2 * 0.8))
            _cx = (x0 + x1) // 2
            x0 = max(0, _cx - _cw2 // 2)
            x1 = min(orig_w, x0 + _cw2)
            if x1 - x0 < _cw2:
                x0 = max(0, x1 - _cw2)
            print(f"    [GUARDRAIL] headroom was {_have*100:.0f}% -> expanded box to ({x0},{y0})-({x1},{y1})")
    except Exception as _e:
        print(f"    [GUARDRAIL] skipped: {_e}")

    return (x0, y0, x1, y1)


def step1_crop(raw_path: str) -> str:
    """Crop raw -> CROPPED/<name>_crop.jpg. Returns cropped path."""
    name = os.path.splitext(os.path.basename(raw_path))[0]
    img = Image.open(raw_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    box = ai_crop_box(img)
    print(f"    [CROP] box={box} ({box[2]-box[0]}x{box[3]-box[1]})")
    cropped = img.crop(box)
    out = os.path.join(DIR_CROP, f"{name}_crop.jpg")
    cropped.save(out, quality=97)
    return out


# ---------------- STEP 2: EDIT BACKEND (gpt-image-2 default, gemini kept as backup) ----------------
EDIT_BACKEND = "gpt"  # "gpt" | "gemini"

GPT_IMG_URL = "https://api.cun.ai/v1/images/edits"
GPT_IMG_KEY = secret("cun_api_key")
GPT_IMG_MODEL = "gpt-image-2.5-sunburst"
GPT_STUDIO_PROMPT = (
    "Studio passport photo 4K HD remaster: "
    "Replace background with uniform vibrant azure sky-blue (#4A9FF5). "
    "Preserve exact original face, beard, hairline, and expression 100% unchanged, no beautification. "
    "Natural balanced skin tone, remove flash glare, soft studio lighting. "
    "Crisp clothing, ultra-sharp 4K details, zero blur, exact framing."
)


def _extract_edit_image(j) -> bytes:
    """Pull the generated image out of an edits response.

    Accepts b64_json (the usual shape) or url (some deployments return that).
    Returns b'' when the body carries no usable image.
    """
    try:
        item = j["data"][0]
    except Exception:
        return b""
    b64 = item.get("b64_json")
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception:
            return b""
    url = item.get("url")
    if url:
        try:
            rr = requests.get(url, timeout=120)
            if rr.status_code == 200 and rr.content:
                return rr.content
        except Exception:
            return b""
    return b""


def step2_gpt_edit(cropped_path: str) -> bytes:
    """Enhance cropped image via gpt-image-2 (cun.ai). Returns image bytes.

    The API occasionally returns a 200 whose body carries no image (transient
    error / moderation shape), so retry a couple of times before giving up.
    """
    with Image.open(cropped_path) as img:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    last = ""
    t_start = time.time()
    for attempt in range(3):
        t_a = time.time()
        last = ""
        try:
            r = requests.post(GPT_IMG_URL,
                headers={"Authorization": f"Bearer {GPT_IMG_KEY}"},
                files={"image": ("photo.png", io.BytesIO(img_bytes), "image/png")},
                data={"model": GPT_IMG_MODEL, "prompt": GPT_STUDIO_PROMPT},
                timeout=240)
        except Exception as e:
            last = f"{e.__class__.__name__}: {e}"
            print(f"    [EDIT] attempt {attempt+1} connection error after "
                  f"{time.time()-t_a:.1f}s ({last[:80]}) -> retrying", flush=True)
            time.sleep(2)
            continue
        el = time.time() - t_a
        if r.status_code == 200:
            try:
                img_out = _extract_edit_image(r.json())
            except Exception as e:
                img_out = b""
                last = f"unreadable body ({e.__class__.__name__})"
            if img_out:
                if attempt:
                    print(f"    [EDIT] attempt {attempt+1} OK after {el:.1f}s "
                          f"(total {time.time()-t_start:.1f}s)", flush=True)
                return img_out
            if not last:
                last = f"no image in body: {r.text[:200]}"
            print(f"    [EDIT] attempt {attempt+1} returned no image after "
                  f"{el:.1f}s -> retrying | {last[:120]}", flush=True)
        else:
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            print(f"    [EDIT] attempt {attempt+1} HTTP {r.status_code} "
                  f"after {el:.1f}s -> retrying", flush=True)
        if attempt < 2:
            time.sleep(2)
    raise RuntimeError(f"image edit failed after 3 attempts: {last}")


# ---------------- STEP 2+3 (legacy): Gemini edit via CDP headless bot ----------------
from gemini_bot import launch_chrome, attach_to_gemini, CDP, _JS_TYPE, _JS_CLICK_SEND  # noqa: E402

EDIT_PROMPT = (
    "পিকচারটা ভালো করে HD করে দিন ব্যাগরাউন আকাশী হবে কিন্তু মুখের ফেস কোন পরিবর্তন হবে না। "
    "ছবির ফ্রেমিং ও জুম হুবহু একই রাখুন, কাছে টেনে টাইট ক্রপ করবেন না — মাথার উপরে ফাঁকা জায়গা রাখুন।"
)

_JS_PROBE_STATE = """(() => {
  const all = document.querySelectorAll('model-response');
  const last = all[all.length - 1];
  if (!last) return JSON.stringify({ n: all.length, txt: '', done: false, hasImg: false });
  const mc = last.querySelector('message-content');
  const txt = mc ? mc.textContent.trim() : '';
  const img = last.querySelector('img');
  const isImgDone = !!(img && img.complete && img.naturalWidth > 0 && !last.querySelector('mat-progress-spinner, [role=progressbar]'));
  const isTextDone = !!last.querySelector('message-actions');
  return JSON.stringify({ n: all.length, txt: txt, done: isTextDone || isImgDone, hasImg: isImgDone });
})()"""


def _paste_image(cdp: CDP, b64: str) -> str:
    cdp.js("window.__uploadB64 = '';")
    CH = 400000
    pos = 0
    while pos < len(b64):
        cdp.js("window.__uploadB64 += " + json.dumps(b64[pos:pos + CH]) + ";")
        pos += CH
    assert cdp.js("window.__uploadB64.length") == len(b64)
    return cdp.js("""(() => {
      try {
        const bytes = Uint8Array.from(atob(window.__uploadB64), c => c.charCodeAt(0));
        const file = new File([bytes], 'photo.jpg', {type: 'image/jpeg'});
        const dt = new DataTransfer();
        dt.items.add(file);
        const ed = document.querySelector('div.ql-editor');
        if (!ed) return 'NO_EDITOR';
        ed.focus();
        ed.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
        return 'pasted';
      } catch (e) { return 'ERR ' + e.message; }
    })()""")


def _extract_last_image(cdp: CDP):
    r = cdp.js("""(() => {
      try {
        const all = document.querySelectorAll('model-response');
        const last = all[all.length - 1];
        const img = last ? last.querySelector('img') : null;
        if (!img || !img.complete || !img.naturalWidth) return 'NO_IMG';
        const c = document.createElement('canvas');
        c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext('2d').drawImage(img, 0, 0);
        window.__imgData = { b64: c.toDataURL('image/png').split(',')[1] };
        return 'ok';
      } catch (e) { return 'ERR ' + e.message; }
    })()""")
    if r != "ok":
        return None
    total = cdp.js("window.__imgData ? window.__imgData.b64.length : 0") or 0
    if not total:
        return None
    chunks, CH, pos = [], 300000, 0
    while pos < total:
        chunks.append(cdp.js(f"window.__imgData.b64.substring({pos}, {pos + CH})"))
        pos += CH
    return base64.b64decode("".join(chunks))


_gemini_lock = threading.Lock()
_cdp = None


def _get_cdp():
    global _cdp
    if _cdp is None:
        launch_chrome()
        _cdp = attach_to_gemini()
    return _cdp


def step2_gemini_edit(cropped_path: str) -> str:
    """Upload cropped image to Gemini, wait for edited output image. Returns b64 png bytes."""
    global _cdp
    with _gemini_lock:
        cdp = _get_cdp()
        for attempt in (1, 2):  # one retry with page reload
            try:
                base = cdp.js("document.querySelectorAll('model-response').length") or 0

                with Image.open(cropped_path) as im:
                    buf = io.BytesIO()
                    im.convert("RGB").save(buf, format="JPEG", quality=95)
                r = _paste_image(cdp, base64.b64encode(buf.getvalue()).decode())
                if r != "pasted":
                    raise RuntimeError(f"paste failed: {r}")
                t0 = time.time()
                while time.time() - t0 < 25:
                    time.sleep(0.5)
                    if cdp.js("!!document.querySelector('uploader-file-preview')"):
                        break

                cdp.js(f"window.__gemini_prompt = {json.dumps(EDIT_PROMPT)}")
                typed = cdp.js(_JS_TYPE)
                if typed in (None, "NO_EDITOR"):
                    raise RuntimeError("editor not found")
                time.sleep(0.2)
                if cdp.js(_JS_CLICK_SEND) != "sent":
                    raise RuntimeError("send button missing")

                # poll for the edited image
                deadline = time.time() + 240
                img_bytes = None
                while time.time() < deadline:
                    time.sleep(0.5)
                    try:
                        state = json.loads(cdp.js(_JS_PROBE_STATE))
                    except Exception:
                        continue
                    if state.get("n", 0) <= base:
                        continue
                    if state.get("hasImg"):
                        img_bytes = _extract_last_image(cdp)
                        if img_bytes:
                            break
                    if state.get("done") and not img_bytes:
                        img_bytes = _extract_last_image(cdp)
                        if img_bytes:
                            break
                        # text-only answer; give it a few more seconds for the image
                        time.sleep(3)
                if not img_bytes:
                    raise RuntimeError("no image in Gemini response (timeout)")
                return img_bytes
            except Exception as e:
                print(f"    [GEMINI] attempt {attempt} failed: {e}")
                log_err(f"gemini attempt {attempt}: {e}")
                try:  # recover: reload the app page
                    cdp.call("Page.navigate", url="https://gemini.google.com/app?hl=en")
                    time.sleep(5)
                    for _ in range(40):
                        if cdp.js("!!document.querySelector('div.ql-editor')"):
                            break
                        time.sleep(0.5)
                except Exception:
                    _cdp = None
                    cdp = _get_cdp()
        raise RuntimeError("Gemini edit failed after retries")


# ---------------- pipeline per file ----------------
def process(raw_path: str):
    name = os.path.splitext(os.path.basename(raw_path))[0]
    t0 = time.time()
    # the file can vanish between being queued and being picked up (the user
    # moves it, or a sync client rewrites it) - skip quietly instead of failing
    if not os.path.exists(raw_path):
        print(f"\n[PIPE] {os.path.basename(raw_path)}")
        print(f"    [SKIP] file disappeared before processing")
        return
    print(f"\n[PIPE] {os.path.basename(raw_path)}")
    try:
        crop_path = step1_crop(raw_path)
        print(f"    [OK] cropped -> {os.path.basename(crop_path)}")

        if EDIT_BACKEND == "gpt":
            png = step2_gpt_edit(crop_path)
        else:
            png = step2_gemini_edit(crop_path)
        final_path = os.path.join(DIR_FINAL, f"{name}_final.jpg")
        im = Image.open(io.BytesIO(png))
        if im.mode in ("RGBA", "P"):
            im = im.convert("RGB")
        # SIZE LOCK: gpt-image-2 returns its own default dimensions — force back
        # to the exact crop size so framing/size never changes.
        with Image.open(crop_path) as _cp:
            _cw, _ch = _cp.size
        if im.size != (_cw, _ch):
            print(f"    [SIZELOCK] gpt returned {im.size[0]}x{im.size[1]} -> resizing to crop size {_cw}x{_ch}")
            im = im.resize((_cw, _ch), Image.Resampling.LANCZOS)
        im.save(final_path, quality=97)
        print(f"    [OK] final   -> {os.path.basename(final_path)} ({im.size[0]}x{im.size[1]})")

        if _SETTINGS.get("keep_original"):
            # Syncthing folder: copy the file out, never move/delete it — else
            # Syncthing re-downloads it and the same photo gets processed again
            dst = os.path.join(DIR_DONE, os.path.basename(raw_path))
            if not os.path.exists(dst):
                shutil.copy2(raw_path, dst)
            add_ledger(os.path.basename(raw_path))
        else:
            shutil.move(raw_path, os.path.join(DIR_DONE, os.path.basename(raw_path)))
        print(f"    [DONE] total {time.time() - t0:.1f}s")
        _notify("done", name, f"({time.time() - t0:.0f}s)")
    except Exception as e:
        print(f"    [FAIL] {e}")
        log_err(f"{os.path.basename(raw_path)}: {e}")
        _notify("fail", name, str(e)[:90])
        if not _SETTINGS.get("keep_original"):
            try:
                shutil.move(raw_path, os.path.join(DIR_FAIL, os.path.basename(raw_path)))
            except Exception:
                pass


def stable(path: str) -> bool:
    """File finished copying? (size unchanged for 1.5s)"""
    try:
        s1 = os.path.getsize(path)
        time.sleep(1.5)
        return os.path.getsize(path) == s1 and s1 > 0
    except Exception:
        return False


def _scanner(seen: set, q):
    """Background thread: announce new arrivals immediately and queue them,
    even while workers are busy with a long process() call."""
    while True:
        try:
            for f in sorted(os.listdir(DIR_INPUT)):
                if not f.lower().endswith(IMG_EXT):
                    continue
                if f in seen:
                    continue
                seen.add(f)
                print(f"[DETECT] {f}", flush=True)
                _notify("detect", f)
                q.put(os.path.join(DIR_INPUT, f))
        except Exception as e:
            log_err(f"scanner: {e}")
        time.sleep(2)


def _worker(q, wid: int):
    """Pull an image off the queue and run the crop+edit pipeline on it."""
    while True:
        item = q.get()
        try:
            if not os.path.exists(item):
                continue
            if not stable(item):
                q.put(item)          # still copying — try again shortly
                time.sleep(2)
                continue
            print(f"[WORKER {wid}] {os.path.basename(item)}", flush=True)
            process(item)
        except Exception as e:
            log_err(f"worker {wid} {os.path.basename(item)}: {e}")
        finally:
            q.task_done()


WORKERS = max(1, int(os.environ.get("PA_WORKERS") or _SETTINGS.get("workers") or 3))


def main():
    for d in (DIR_INPUT, DIR_CROP, DIR_FINAL, DIR_DONE, DIR_FAIL):
        os.makedirs(d, exist_ok=True)
    print("=" * 60)
    print("PASSPORT AUTO PIPELINE — folder watcher")
    print(f"  INPUT  : {DIR_INPUT}")
    print(f"  CROPPED: {DIR_CROP}")
    print(f"  FINAL  : {DIR_FINAL}")
    print(f"  WORKERS: {WORKERS} (parallel)")
    if _SETTINGS.get("keep_original"):
        print("  MODE   : keep original (source files are copied, never moved)")
    print("=" * 60)
    print("Drop raw camera images into INPUT — processing starts automatically.\n")
    _notify("start", "watcher online", f"{WORKERS} workers")

    keep = bool(_SETTINGS.get("keep_original"))
    seen = load_ledger() if keep else set()

    # First run on a shared/camera folder: don't run the whole existing library
    # through the paid API. Mark everything already there as handled, so only
    # photos taken from now on get processed.
    if keep and not seen and not _SETTINGS.get("process_existing"):
        try:
            existing = [f for f in os.listdir(DIR_INPUT) if f.lower().endswith(IMG_EXT)]
        except Exception:
            existing = []
        for f in existing:
            add_ledger(f)
        seen = set(existing)
        print(f"[BASELINE] {len(existing)} existing file(s) skipped — "
              f"only NEW photos will be processed", flush=True)

    q = queue.Queue()
    for i in range(WORKERS):
        threading.Thread(target=_worker, args=(q, i + 1), daemon=True).start()
    threading.Thread(target=_scanner, args=(seen, q), daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
