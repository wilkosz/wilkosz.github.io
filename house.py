#!/usr/bin/env python3
"""Merge one house-research run into data/house.json, write a log, rebuild.

    python3 house.py path/to/run.json

Run file shape (all keys optional except as_of):
{
  "as_of": "2026-09-28T09:00",              # UTC, ISO-ish
  "summary": "the current recommendation, 2-4 sentences",
  "headlines": ["..."],                      # 3-6 one-liners: what changed since the last run
  "options": [                               # upsert by key; 'first_seen' is preserved
    {"key": "fairdinkum-3bed", "type": "shed-home",
     "title": "Fair Dinkum Homes 3-bed", "supplier": "Fair Dinkum Builds",
     "url": "https://...", "bedrooms": 3, "bathrooms": 1, "size_m2": 120,
     "kit_price_aud": 65000, "price_note": "what the price includes",
     "lead_time": "12-16 weeks",
     "cost_lines": [{"item": "kit", "low": 60000, "high": 65000, "note": "source or estimate basis"}],
     "logistics": ["..."], "pros": ["..."], "cons": ["..."],
     "verdict": "best|viable|marginal|no", "why": "one sentence",
     "sources": ["https://..."]},
    {"key": "old-option", "remove": true, "reason": "discontinued"}
  ],
  "site_costs": [{"key": "solar-battery", "item": "...", "low": 35000, "high": 55000, "note": "..."}],
  "site": [{"topic": "Flood", "finding": "...", "source": "https://..."}],
  "logistics": [{"topic": "Oversize loads", "finding": "...", "source": "https://..."}],
  "open_questions": ["..."],
  "crew": {                                  # the crew-housing cycle (brief: house-brief.json 'crew')
    "summary": "best way to house rotating team members under the cap, 2-4 sentences",
    "headlines": ["..."],
    "options": [                             # upsert by key, same rules as options above
      {"key": "gumtree-3bed-donga", "type": "donga", "title": "...", "url": "https://...",
       "where": "on the block", "bedrooms": 3, "bathrooms": 1, "size_m2": 72,
       "standard": "one line: aircon, insulation, kitchen, bathroom, condition",
       "cost_lines": [{"item": "...", "low": 0, "high": 0, "note": "..."}],   # ALL-IN upfront
       "running": [{"item": "...", "low": 0, "high": 0, "note": "..."}],      # per year
       "pros": [], "cons": [], "verdict": "best|viable|marginal|no", "why": "...", "sources": []}
    ],
    "questions": ["..."]                     # replaces the stored list when sent
  },
  "notes": "free-form markdown appended to the log"
}

site_costs, site, logistics and open_questions replace the stored lists when sent.
An option's landed total = its cost_lines + every site_costs line (build.py adds them up).
A crew option is all-in on its own: its cost_lines already carry any power, water and
wastewater it needs, and site_costs are not added.

Owner-maintained: data/house-brief.json (edit directly when the owner asks in chat).
Agent-maintained: data/house.json, house/*.md
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
LOGS = os.path.join(ROOT, "house")

MAX_OPTIONS = 12
VERDICTS = ("best", "viable", "marginal", "no")
TYPES = ("shed-home", "kit-home", "modular", "transportable", "relocated", "container", "owner-build", "other")
CREW_TYPES = TYPES + ("rental", "town-house", "donga", "cabin", "caravan")


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


def check_lines(where, lines):
    for ln in lines:
        if not ln.get("item"):
            fail("%s cost line missing 'item': %r" % (where, ln))
        for k in ("low", "high"):
            if not isinstance(ln.get(k), (int, float)):
                fail("%s cost line %r needs numeric %r" % (where, ln.get("item"), k))
        if ln["low"] > ln["high"]:
            fail("%s cost line %r has low > high" % (where, ln["item"]))


def total(lines):
    return sum(ln["low"] for ln in lines), sum(ln["high"] for ln in lines)


def dollars(x):
    return "$%s" % format(int(round(x)), ",d")


def merge_options(stored, items, types, label, day, changes):
    """Upsert run options into the stored list by key; rank and cap. label is 'house' or 'crew'."""
    by_key = {o["key"]: o for o in stored}
    for item in items or []:
        if not item.get("key"):
            fail("%s option missing 'key': %r" % (label, item))
        key = slug(item["key"])
        if item.get("remove"):
            if key in by_key:
                gone = by_key.pop(key)
                changes.append("- %s: removed %s - %s" % (
                    label, gone.get("title", key), item.get("reason", "no reason given")))
            continue
        if item.get("verdict") and item["verdict"] not in VERDICTS:
            fail("%s option %s verdict must be one of %s" % (label, key, VERDICTS))
        if item.get("type") and item["type"] not in types:
            fail("%s option %s type must be one of %s" % (label, key, types))
        if item.get("cost_lines") is not None:
            check_lines("%s option %s" % (label, key), item["cost_lines"])
        prev = by_key.get(key)
        entry = dict(prev or {})
        entry.update({k: v for k, v in item.items() if k != "remove"})
        entry["key"] = key
        entry["first_seen"] = (prev or {}).get("first_seen") or day
        entry["updated"] = day
        for k in ("title", "type", "url", "verdict", "cost_lines"):
            if k not in entry:
                fail("%s option %s missing %r" % (label, key, k))
        by_key[key] = entry
        lo, hi = total(entry["cost_lines"])
        if prev is None:
            changes.append("- %s: new %s: %s - %s-%s (%s)" % (
                label, entry["type"], entry["title"], dollars(lo), dollars(hi), entry["verdict"]))
        else:
            plo, phi = total(prev.get("cost_lines", []))
            if (plo, phi) != (lo, hi):
                changes.append("- %s: %s cost %s-%s -> %s-%s" % (
                    label, entry["title"], dollars(plo), dollars(phi), dollars(lo), dollars(hi)))
            if prev.get("verdict") != entry["verdict"]:
                changes.append("- %s: %s: %s -> %s" % (label, entry["title"], prev.get("verdict"), entry["verdict"]))

    # rank: verdict, then cheapest low end; keep the best MAX_OPTIONS
    rank = {v: i for i, v in enumerate(VERDICTS)}
    options = sorted(by_key.values(), key=lambda o: (rank.get(o.get("verdict"), 9), total(o["cost_lines"])[0]))
    for o in options[MAX_OPTIONS:]:
        changes.append("- %s: dropped %s (over %d-option cap)" % (label, o["title"], MAX_OPTIONS))
    return options[:MAX_OPTIONS]


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

    doc = load("house.json", {"as_of": None, "summary": "", "headlines": [], "options": [],
                              "site_costs": [], "site": [], "logistics": [], "open_questions": []})
    doc["as_of"] = as_of
    if run.get("summary"):
        doc["summary"] = run["summary"].strip()
    if run.get("headlines") is not None:
        doc["headlines"] = [str(x).strip() for x in run["headlines"] if str(x).strip()][:6]

    if run.get("site_costs") is not None:
        check_lines("site_costs", run["site_costs"])
        doc["site_costs"] = run["site_costs"]
    for k in ("site", "logistics"):
        if run.get(k) is not None:
            for it in run[k]:
                if not it.get("topic") or not it.get("finding"):
                    fail("%s item needs 'topic' and 'finding': %r" % (k, it))
            doc[k] = run[k]
    if run.get("open_questions") is not None:
        doc["open_questions"] = [str(q).strip() for q in run["open_questions"] if str(q).strip()]

    changes = []
    doc["options"] = merge_options(doc.get("options", []), run.get("options"), TYPES, "house", day, changes)

    crew_run = run.get("crew")
    if crew_run is not None:
        crew = doc.setdefault("crew", {"summary": "", "headlines": [], "options": [], "questions": []})
        if crew_run.get("summary"):
            crew["summary"] = crew_run["summary"].strip()
        if crew_run.get("headlines") is not None:
            crew["headlines"] = [str(x).strip() for x in crew_run["headlines"] if str(x).strip()][:6]
        if crew_run.get("questions") is not None:
            crew["questions"] = [str(q).strip() for q in crew_run["questions"] if str(q).strip()]
        for o in crew_run.get("options") or []:
            if o.get("running") is not None:
                check_lines("crew %s running" % o.get("key"), o["running"])
        crew["options"] = merge_options(crew.get("options", []), crew_run.get("options"),
                                        CREW_TYPES, "crew", day, changes)
    save("house.json", doc)

    # --- log
    os.makedirs(LOGS, exist_ok=True)
    slo, shi = total(doc.get("site_costs", []))
    lines = ["# House research %s UTC" % as_of, ""]
    if doc.get("headlines"):
        lines += ["## What changed", ""] + ["- " + h for h in doc["headlines"]] + [""]
    if doc.get("summary"):
        lines += ["## Recommendation", "", doc["summary"], ""]
    if changes:
        lines += ["## Changes", ""] + changes + [""]
    lines += ["## Options, cheapest landed first", "",
              "Off-grid and site works add %s-%s to every option." % (dollars(slo), dollars(shi)), ""]
    for o in doc["options"]:
        lo, hi = total(o["cost_lines"])
        lines.append("- [%s] %s - landed %s-%s <%s>" % (
            o["verdict"], o["title"], dollars(lo + slo), dollars(hi + shi), o.get("url", "")))
    lines.append("")
    crew = doc.get("crew") or {}
    if crew.get("options"):
        lines += ["## Crew housing, cheapest upfront first", ""]
        if crew.get("summary"):
            lines += [crew["summary"], ""]
        for o in crew["options"]:
            lo, hi = total(o["cost_lines"])
            rlo, rhi = total(o.get("running", []))
            lines.append("- [%s] %s - upfront %s-%s, %s-%s a year <%s>" % (
                o["verdict"], o["title"], dollars(lo), dollars(hi), dollars(rlo), dollars(rhi), o.get("url", "")))
        lines.append("")
    if run.get("notes"):
        lines += ["## Notes", "", run["notes"].strip(), ""]
    log_path = os.path.join(LOGS, "%s.md" % stamp)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("wrote %s (%d options, %d crew options, %d changes)" % (
        os.path.relpath(log_path, ROOT), len(doc["options"]), len(crew.get("options", [])), len(changes)))
    subprocess.check_call([sys.executable, os.path.join(ROOT, "build.py")])


if __name__ == "__main__":
    main()
