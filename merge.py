#!/usr/bin/env python3
"""Merge one research run into data/*.json, write a research log, rebuild the site.

    python3 merge.py path/to/run.json

Run file shape (all keys optional except as_of):
{
  "as_of": "2026-08-25T08:00",            # UTC, ISO-ish
  "market_summary": "...",                 # replaces data/status.json market_summary
  "takes": {                               # merged over existing takes, keyed by holding ticker
    "AMZN": {"take": "hold|add|trim|watch", "reason": "...", "price_usd": 123.4}
  },
  "watchlist": [                           # upsert by (ticker, exchange); 'added' is preserved
    {"ticker": "X", "exchange": "US", "name": "...", "sector": "AI|Internet|Machinery|Energy",
     "status": "buy|accumulate|watch|avoid", "conviction": "high|medium|low",
     "thesis": "...", "risks": "...", "price_usd": 1.0, "catalyst": "...", "source": "https://..."},
    {"ticker": "Y", "exchange": "US", "remove": true, "reason": "why it was dropped"}
  ],
  "news": [                                # prepended; deduped by source URL; capped
    {"date": "2026-08-25", "ticker": "NVDA", "headline": "...", "summary": "...",
     "source": "https://...", "impact": "positive|negative|neutral"}
  ],
  "indicators": {                          # optional; upsert by key into data/indicators.json
    "explainer": "...",                    # replaces the explainer if given
    "items": [{"key": "h100_hour", "name": "...", "value": "$2.10", "trend": "down", "signal": "bearish",
               "why": "...", "watch": "...", "note": "...", "source": "https://..."}]
  },
  "notes": "free-form markdown appended to the research log"
}
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RESEARCH = os.path.join(ROOT, "research")

MAX_WATCHLIST = 15
MAX_NEWS_ITEMS = 80
MAX_NEWS_AGE_DAYS = 45


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


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        run = json.load(f)

    as_of = run.get("as_of") or datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
    day = as_of[:10]
    stamp = re.sub(r"[^0-9T]", "", as_of[:16]).replace("T", "-")  # 20260825-0800
    stamp = "%s-%s-%s-%s" % (stamp[0:4], stamp[4:6], stamp[6:8], stamp[9:13])

    holdings = load("holdings.json", [])
    held = {h["ticker"] for h in holdings}
    status = load("status.json", {"as_of": None, "market_summary": "", "takes": {}})
    watchlist = load("watchlist.json", [])
    news = load("news.json", [])
    indicators = load("indicators.json", {"as_of": None, "explainer": "", "indicators": []})

    # --- status
    status["as_of"] = as_of
    if run.get("market_summary"):
        status["market_summary"] = run["market_summary"].strip()
    takes = status.setdefault("takes", {})
    for ticker, t in (run.get("takes") or {}).items():
        if ticker not in held:
            print("skip take for non-holding %s" % ticker)
            continue
        cur = takes.get(ticker, {})
        cur.update({k: v for k, v in t.items() if v is not None or k == "price_usd"})
        cur["updated"] = day
        takes[ticker] = cur

    # --- watchlist
    by_key = {(w["ticker"], w["exchange"]): w for w in watchlist}
    changes = []
    for w in run.get("watchlist") or []:
        key = (w["ticker"], w.get("exchange", "US"))
        if w.get("remove"):
            if key in by_key:
                del by_key[key]
                changes.append("- removed %s:%s - %s" % (key[0], key[1], w.get("reason", "")))
            continue
        if key[0] in held:
            print("skip watchlist entry for holding %s" % key[0])
            continue
        prev = by_key.get(key)
        entry = dict(prev or {})
        entry.update({k: v for k, v in w.items() if k != "remove"})
        entry.setdefault("exchange", key[1])
        entry["added"] = (prev or {}).get("added") or day
        entry["updated"] = day
        by_key[key] = entry
        if prev is None:
            changes.append("- added %s:%s (%s, %s conviction)" % (key[0], key[1], entry.get("status"), entry.get("conviction")))
        elif prev.get("status") != entry.get("status") or prev.get("conviction") != entry.get("conviction"):
            changes.append("- %s:%s %s/%s -> %s/%s" % (key[0], key[1], prev.get("status"), prev.get("conviction"),
                                                       entry.get("status"), entry.get("conviction")))
    watchlist = list(by_key.values())
    if len(watchlist) > MAX_WATCHLIST:
        order = {"buy": 0, "accumulate": 1, "watch": 2, "avoid": 3}
        conv = {"high": 0, "medium": 1, "low": 2}
        watchlist.sort(key=lambda w: (order.get(w["status"], 9), conv.get(w["conviction"], 9), w["updated"]))
        for w in watchlist[MAX_WATCHLIST:]:
            changes.append("- dropped %s:%s (over %d-entry cap)" % (w["ticker"], w["exchange"], MAX_WATCHLIST))
        watchlist = watchlist[:MAX_WATCHLIST]
    watchlist.sort(key=lambda w: (w["sector"], w["ticker"]))

    # --- news
    seen = {n["source"] for n in news}
    fresh = []
    for n in run.get("news") or []:
        if n["source"] in seen:
            continue
        seen.add(n["source"])
        fresh.append(n)
    cutoff = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=MAX_NEWS_AGE_DAYS)).strftime("%Y-%m-%d")
    fresh = [n for n in fresh if n["date"] >= cutoff]
    news = [n for n in fresh + news if n["date"] >= cutoff]
    news.sort(key=lambda n: n["date"], reverse=True)
    news = news[:MAX_NEWS_ITEMS]

    # --- indicators
    ind_changes = []
    ind_run = run.get("indicators") or {}
    if ind_run:
        indicators["as_of"] = day
        if ind_run.get("explainer"):
            indicators["explainer"] = ind_run["explainer"].strip()
        by_k = {i["key"]: i for i in indicators.get("indicators", [])}
        for i in ind_run.get("items") or []:
            prev = by_k.get(i["key"])
            entry = dict(prev or {})
            entry.update(i)
            entry["updated"] = day
            by_k[i["key"]] = entry
            if prev is None:
                ind_changes.append("- added %s: %s (%s, %s)" % (i["key"], entry.get("value"), entry.get("trend"), entry.get("signal")))
            elif prev.get("value") != entry.get("value") or prev.get("signal") != entry.get("signal"):
                ind_changes.append("- %s: %s/%s -> %s/%s" % (i["key"], prev.get("value"), prev.get("signal"), entry.get("value"), entry.get("signal")))
        indicators["indicators"] = list(by_k.values())
        save("indicators.json", indicators)

    save("status.json", status)
    save("watchlist.json", watchlist)
    save("news.json", news)

    # --- research log
    os.makedirs(RESEARCH, exist_ok=True)
    lines = ["# Research run %s UTC" % as_of, ""]
    if status.get("market_summary"):
        lines += ["## Market summary", "", status["market_summary"], ""]
    if run.get("takes"):
        lines += ["## Holdings", ""]
        for ticker, t in sorted(run["takes"].items()):
            if ticker not in held:
                continue
            price = t.get("price_usd")
            lines.append("- %s: %s%s - %s" % (ticker, t.get("take"), (" @ $%s" % price) if price is not None else "", t.get("reason", "")))
        lines.append("")
    if changes:
        lines += ["## Watchlist changes", ""] + changes + [""]
    lines += ["## Watchlist", ""]
    for w in watchlist:
        lines.append("- %s:%s %s - %s (%s) - %s" % (w["ticker"], w["exchange"], w["name"], w["status"], w["conviction"], w["thesis"]))
    lines.append("")
    if ind_changes:
        lines += ["## Bellwether changes", ""] + ind_changes + [""]
    if fresh:
        lines += ["## New news (%d)" % len(fresh), ""]
        for n in fresh:
            lines.append("- %s [%s] %s: %s - %s <%s>" % (n["date"], n["impact"], n["ticker"], n["headline"], n["summary"], n["source"]))
        lines.append("")
    if run.get("notes"):
        lines += ["## Notes", "", run["notes"].strip(), ""]
    log_path = os.path.join(RESEARCH, "%s.md" % stamp)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote %s (%d new news, %d watchlist changes, %d bellwether changes)" % (os.path.relpath(log_path, ROOT), len(fresh), len(changes), len(ind_changes)))

    subprocess.check_call([sys.executable, os.path.join(ROOT, "build.py")])


if __name__ == "__main__":
    main()
