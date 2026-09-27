#!/usr/bin/env python3
"""Merge one asset-hunt run into data/finds.json, fetch photos, write a log, rebuild.

    python3 hunt.py path/to/run.json

Run file shape (all keys optional except as_of):
{
  "as_of": "2026-09-28T09:00",             # UTC, ISO-ish
  "summary": "one paragraph on the state of the hunt",
  "headlines": ["..."],                     # 3-6 one-liners: what changed since the last run
  "finds": [                                # upsert by key; 'first_seen' is preserved
    {"key": "grays-1234567", "want": "tractor",
     "title": "2016 John Deere 5100M",
     "price_aud": 62000, "price_note": "plus 5.5% buyer premium",
     "location": "Wagga Wagga, NSW", "distance_km": 138,
     "detail": ["3,200 hours", "FEL with 4-in-1 bucket", "no AdBlue"],
     "source": "Grays", "url": "https://...",
     "photo_url": "https://.../photo.jpg",   # a fetchable image URL, or
     "photo_file": "/tmp/.../shot.png",      # a local image (cropped screenshot) - wins if both

     "verdict": "strong|decent|stretch", "why": "one sentence on why it is worth it",
     "status": "live|sold|gone", "ends": "2026-10-02"},
    {"key": "fb-999", "remove": true, "reason": "sold"}
  ],
  "notes": "free-form markdown appended to the hunt log"
}

Owner-maintained: data/wants.json (edit directly when the owner asks in chat).
Agent-maintained: data/finds.json, img/finds/*, hunt/*.md
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
HUNT = os.path.join(ROOT, "hunt")
IMG = os.path.join(ROOT, "img", "finds")

MAX_FINDS_PER_WANT = 6
MAX_GONE_AGE_DAYS = 7
THUMB_PX = 400
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
VERDICTS = ("strong", "decent", "stretch")
FIND_STATUSES = ("live", "sold", "gone")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def load(name, default):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def fail(msg):
    print("INVALID: " + msg, file=sys.stderr)
    sys.exit(1)


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return s[:60] or "item"


def shrink(raw, key):
    """Normalise to a THUMB_PX jpeg via sips (macOS). Returns a site-relative path."""
    if shutil.which("sips"):
        jpg = os.path.join(IMG, key + ".jpg")
        try:
            subprocess.run(["sips", "-s", "format", "jpeg", "-Z", str(THUMB_PX), raw, "--out", jpg],
                           check=True, capture_output=True)
            if raw != jpg:
                os.remove(raw)
            return "img/finds/%s" % os.path.basename(jpg)
        except subprocess.CalledProcessError as ex:
            print("  photo %s: sips failed (%s), keeping original" % (key, ex))
    return "img/finds/%s" % os.path.basename(raw)


def copy_photo(key, path):
    """Take a photo already on disk (e.g. a cropped browser screenshot)."""
    if not os.path.exists(path):
        print("  photo %s: %s not found" % (key, path))
        return None
    os.makedirs(IMG, exist_ok=True)
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    raw = os.path.join(IMG, key + ext)
    shutil.copyfile(path, raw)
    return shrink(raw, key)


def fetch_photo(key, url):
    """Download url into img/finds/<key>.<ext>, shrink to THUMB_PX. Returns a
    site-relative path, or None if anything went wrong (a find without a photo
    still renders)."""
    os.makedirs(IMG, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*"})
        with urllib.request.urlopen(req, timeout=30) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in EXT_BY_TYPE:
                print("  photo %s: not an image (%s)" % (key, ctype or "unknown type"))
                return None
            blob = r.read(MAX_DOWNLOAD_BYTES + 1)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as ex:
        print("  photo %s: download failed (%s)" % (key, ex))
        return None
    if len(blob) > MAX_DOWNLOAD_BYTES:
        print("  photo %s: over %d MB, skipped" % (key, MAX_DOWNLOAD_BYTES // (1024 * 1024)))
        return None

    raw = os.path.join(IMG, key + EXT_BY_TYPE[ctype])
    with open(raw, "wb") as f:
        f.write(blob)
    return shrink(raw, key)


def prune_images(finds):
    """Delete thumbnails no longer referenced by any find."""
    if not os.path.isdir(IMG):
        return 0
    keep = {os.path.basename(f["photo"]) for f in finds if f.get("photo")}
    dropped = 0
    for name in os.listdir(IMG):
        if name not in keep:
            os.remove(os.path.join(IMG, name))
            dropped += 1
    return dropped


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        run = json.load(f)

    as_of = run.get("as_of") or datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
    day = as_of[:10]
    stamp = re.sub(r"[^0-9T]", "", as_of[:16]).replace("T", "-")
    stamp = "%s-%s-%s-%s" % (stamp[0:4], stamp[4:6], stamp[6:8], stamp[9:13])

    wants = load("wants.json", {"wants": []})
    want_keys = {w["key"] for w in wants.get("wants", [])}
    doc = load("finds.json", {"as_of": None, "summary": "", "headlines": [], "finds": []})
    finds = doc.get("finds", [])

    doc["as_of"] = as_of
    if run.get("summary"):
        doc["summary"] = run["summary"].strip()
    if run.get("headlines") is not None:
        doc["headlines"] = [str(x).strip() for x in run["headlines"] if str(x).strip()][:6]

    by_key = {f["key"]: f for f in finds}
    changes = []
    photos = 0

    for item in run.get("finds") or []:
        if not item.get("key"):
            fail("find missing 'key': %r" % item)
        key = slug(item["key"])

        if item.get("remove"):
            if key in by_key:
                gone = by_key.pop(key)
                changes.append("- removed %s (%s) - %s" % (gone.get("title", key), gone.get("want", "?"),
                                                           item.get("reason", "no reason given")))
            continue

        if item.get("want") and item["want"] not in want_keys:
            fail("find %s references unknown want %r (not in wants.json)" % (key, item["want"]))
        if item.get("verdict") and item["verdict"] not in VERDICTS:
            fail("find %s verdict must be one of %s" % (key, VERDICTS))
        if item.get("status") and item["status"] not in FIND_STATUSES:
            fail("find %s status must be one of %s" % (key, FIND_STATUSES))

        prev = by_key.get(key)
        entry = dict(prev or {})
        entry.update({k: v for k, v in item.items() if k not in ("remove", "photo_url", "photo_file")})
        entry["key"] = key
        entry.setdefault("status", "live")
        entry["first_seen"] = (prev or {}).get("first_seen") or day
        entry["updated"] = day

        photo_url, photo_file = item.get("photo_url"), item.get("photo_file")
        if photo_file:
            # a local image, e.g. a cropped screenshot of a Facebook listing
            path = copy_photo(key, photo_file)
            if path:
                entry["photo"] = path
                photos += 1
        elif photo_url and (photo_url != (prev or {}).get("photo_url") or not entry.get("photo")):
            path = fetch_photo(key, photo_url)
            if path:
                entry["photo"] = path
                entry["photo_url"] = photo_url
                photos += 1
        by_key[key] = entry

        if prev is None:
            changes.append("- new %s: %s - %s%s" % (
                entry.get("want", "?"), entry.get("title", key),
                ("$%s" % format(entry["price_aud"], ",d")) if isinstance(entry.get("price_aud"), int) else "price TBC",
                (" (%s)" % entry["verdict"]) if entry.get("verdict") else ""))
        else:
            if prev.get("price_aud") != entry.get("price_aud"):
                changes.append("- %s: price %s -> %s" % (entry.get("title", key), prev.get("price_aud"), entry.get("price_aud")))
            if prev.get("status") != entry.get("status"):
                changes.append("- %s: %s -> %s" % (entry.get("title", key), prev.get("status"), entry.get("status")))

    finds = list(by_key.values())

    # drop finds for wants the owner has deleted
    orphans = [f for f in finds if f.get("want") not in want_keys]
    for f in orphans:
        changes.append("- dropped %s (want %r no longer in wants.json)" % (f.get("title", f["key"]), f.get("want")))
    finds = [f for f in finds if f.get("want") in want_keys]

    # age out sold/gone
    cutoff = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=MAX_GONE_AGE_DAYS)).strftime("%Y-%m-%d")
    stale = {f["key"] for f in finds if f.get("status") != "live" and f.get("updated", day) < cutoff}
    for f in finds:
        if f["key"] in stale:
            changes.append("- aged out %s (%s for over %d days)" % (f.get("title", f["key"]), f.get("status"), MAX_GONE_AGE_DAYS))
    finds = [f for f in finds if f["key"] not in stale]

    # cap live finds per want: best verdict first, then cheapest, then nearest
    rank = {v: i for i, v in enumerate(VERDICTS)}
    kept = []
    for wk in want_keys:
        live = [f for f in finds if f.get("want") == wk and f.get("status") == "live"]
        rest = [f for f in finds if f.get("want") == wk and f.get("status") != "live"]
        live.sort(key=lambda f: (rank.get(f.get("verdict"), 9),
                                 f.get("price_aud") if f.get("price_aud") is not None else 10 ** 9,
                                 f.get("distance_km") if f.get("distance_km") is not None else 10 ** 9))
        for f in live[MAX_FINDS_PER_WANT:]:
            changes.append("- dropped %s (over %d-find cap for %s)" % (f.get("title", f["key"]), MAX_FINDS_PER_WANT, wk))
        kept += live[:MAX_FINDS_PER_WANT] + rest
    finds = kept
    finds.sort(key=lambda f: (f.get("want", ""), rank.get(f.get("verdict"), 9),
                              f.get("price_aud") if f.get("price_aud") is not None else 10 ** 9))

    removed_imgs = prune_images(finds)
    doc["finds"] = finds
    save("finds.json", doc)

    # --- hunt log
    os.makedirs(HUNT, exist_ok=True)
    lines = ["# Asset hunt %s UTC" % as_of, ""]
    if doc.get("headlines"):
        lines += ["## What changed", ""] + ["- " + h for h in doc["headlines"]] + [""]
    if doc.get("summary"):
        lines += ["## Summary", "", doc["summary"], ""]
    if changes:
        lines += ["## Changes", ""] + changes + [""]
    lines += ["## Live list", ""]
    for w in wants.get("wants", []):
        live = [f for f in finds if f.get("want") == w["key"] and f.get("status") == "live"]
        lines.append("### %s (%d live)" % (w["title"], len(live)))
        for f in live:
            price = ("$%s" % format(f["price_aud"], ",d")) if isinstance(f.get("price_aud"), int) else "price TBC"
            lines.append("- [%s] %s - %s - %s - %s <%s>" % (
                f.get("verdict", "?"), f.get("title", f["key"]), price,
                f.get("location", "location TBC"), f.get("source", "?"), f.get("url", "")))
        lines.append("")
    if run.get("notes"):
        lines += ["## Notes", "", run["notes"].strip(), ""]
    log_path = os.path.join(HUNT, "%s.md" % stamp)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    live_total = len([f for f in finds if f.get("status") == "live"])
    print("wrote %s (%d live finds, %d changes, %d photos fetched, %d thumbnails pruned)" % (
        os.path.relpath(log_path, ROOT), live_total, len(changes), photos, removed_imgs))

    subprocess.check_call([sys.executable, os.path.join(ROOT, "build.py")])


if __name__ == "__main__":
    main()
