#!/usr/bin/env python3
"""Build wilkosz.com.au from data/*.json + research/*.md.

Text-only, no dependencies beyond the Python stdlib.

    python3 build.py          # writes index.html, one page per section, research/ and hunt/
    python3 build.py --check  # validate data files only, no output

Owner-maintained:  data/profile.json  data/holdings.json  data/loves.json
Agent-maintained:  data/status.json   data/watchlist.json data/news.json  research/*.md
"""
import glob
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RESEARCH = os.path.join(ROOT, "research")
HUNT = os.path.join(ROOT, "hunt")
BUYS = os.path.join(ROOT, "buys")

SECTORS = ("AI", "Internet", "Machinery", "Energy")
TAKES = ("hold", "add", "trim", "watch")
STATUSES = ("buy", "accumulate", "watch", "avoid")
CONVICTIONS = ("high", "medium", "low")
IMPACTS = ("positive", "negative", "neutral")
TRENDS = ("up", "flat", "down")
SIGNALS = ("bullish", "neutral", "bearish")
EVENT_TYPES = ("earnings", "macro", "central_bank", "product", "conference", "other")
WANT_STATUSES = ("hunting", "paused", "done")
VERDICTS = ("strong", "decent", "stretch")
FIND_STATUSES = ("live", "sold", "gone")
CALENDAR_DAYS = 14
MAX_NEWS_ON_PAGE = 60


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def e(s):
    return html.escape("" if s is None else str(s))


def link(url, label=None):
    if not url:
        return e(label or "")
    return '<a href="%s">%s</a>' % (e(url), e(label or url))


def money(x):
    if x is None:
        return "-"
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "-"
    return "$%s" % format(x, ",.2f")


def aud(x):
    """Whole-dollar AUD, for buy-list items. (Holdings never show dollars.)"""
    if x is None:
        return "price TBC"
    try:
        return "$%s" % format(int(round(float(x))), ",d")
    except (TypeError, ValueError):
        return e(x)


def band(w):
    lo, hi = w.get("price_min"), w.get("price_max")
    if lo is None and hi is None:
        return "open on price"
    if lo is None:
        return "up to %s" % aud(hi)
    if hi is None:
        return "from %s" % aud(lo)
    return "%s to %s" % (aud(lo), aud(hi))


def where(w, bases):
    base = bases.get(w.get("base"), {}).get("label") or w.get("base") or "anywhere"
    return "within %skm of %s" % (e(w.get("max_km", "?")), e(base))


# ---------------------------------------------------------------- validation
DOLLARS = re.compile(r"\$\s?([\d,]*\.?\d+)(?!\d|[.,]\d|\s*(?:[kKMBT]\b|bn|mn|billion|million|trillion))")


def price_leak(text, price):
    """The first $ figure in text that looks like the holding's share price (within
    0.67x-1.5x of price_usd), or None. Holdings never show prices on the site.
    Analyst price targets are allowed: a figure with "target" close by is skipped."""
    if not text or not price:
        return None
    for m in DOLLARS.finditer(text):
        if "target" in text[max(0, m.start() - 40):m.end() + 15].lower():
            continue
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if 0.67 <= amount / float(price) <= 1.5:
            return m.group(0)
    return None


def holding_price_leaks(holdings, takes, news):
    """[(where, figure)] for any holding take reason or holding news item quoting a share price."""
    held = {h["ticker"] for h in holdings}
    prices = {t: v.get("price_usd") for t, v in takes.items()}
    out = []
    for t, v in takes.items():
        leak = price_leak(v.get("reason"), prices.get(t))
        if t in held and leak:
            out.append(("take %s" % t, leak))
    for n in news:
        if n.get("ticker") in held:
            leak = price_leak("%s %s" % (n.get("headline"), n.get("summary")), prices.get(n["ticker"]))
            if leak:
                out.append(("news %s %s" % (n["ticker"], n.get("date")), leak))
    return out


def fail(msg):
    print("INVALID: " + msg, file=sys.stderr)
    sys.exit(1)


def validate(profile, holdings, loves, status, watchlist, news, indicators=None, calendar=None,
             wants=None, finds=None):
    want_keys = set()
    for w in (wants or {}).get("wants", []):
        for k in ("key", "title", "short", "status", "base", "max_km"):
            if k not in w:
                fail("wants.json %s missing %r" % (w.get("key"), k))
        if w["status"] not in WANT_STATUSES:
            fail("wants.json %s status must be one of %s" % (w["key"], WANT_STATUSES))
        if w["base"] not in (wants or {}).get("bases", {}):
            fail("wants.json %s base %r not in bases" % (w["key"], w["base"]))
        if w["key"] in want_keys:
            fail("wants.json duplicate key %r" % w["key"])
        want_keys.add(w["key"])
    seen_finds = set()
    for f in (finds or {}).get("finds", []):
        for k in ("key", "want", "title", "url", "source"):
            if k not in f:
                fail("finds.json %s missing %r" % (f.get("key"), k))
        if f["want"] not in want_keys:
            fail("finds.json %s references unknown want %r" % (f["key"], f["want"]))
        if f.get("verdict") and f["verdict"] not in VERDICTS:
            fail("finds.json %s verdict must be one of %s" % (f["key"], VERDICTS))
        if f.get("status", "live") not in FIND_STATUSES:
            fail("finds.json %s status must be one of %s" % (f["key"], FIND_STATUSES))
        if f["key"] in seen_finds:
            fail("finds.json duplicate key %r" % f["key"])
        seen_finds.add(f["key"])
    for ev in (calendar or {}).get("events", []):
        for k in ("key", "date", "time", "ticker", "title", "type", "why"):
            if k not in ev:
                fail("calendar.json event missing %r: %r" % (k, ev))
        if ev["type"] not in EVENT_TYPES:
            fail("calendar.json %s type must be one of %s" % (ev["key"], EVENT_TYPES))
        try:
            datetime.strptime(ev["date"], "%Y-%m-%d")
        except ValueError:
            fail("calendar.json bad date %r" % ev["date"])
    for i in (indicators or {}).get("indicators", []):
        for k in ("key", "name", "value", "trend", "signal", "why", "watch", "source", "updated"):
            if k not in i:
                fail("indicators.json %s missing %r" % (i.get("key"), k))
        if i["trend"] not in TRENDS:
            fail("indicators.json %s trend must be one of %s" % (i["key"], TRENDS))
        if i["signal"] not in SIGNALS:
            fail("indicators.json %s signal must be one of %s" % (i["key"], SIGNALS))
    for h in holdings:
        for k in ("ticker", "exchange", "name", "units", "sector"):
            if k not in h:
                fail("holdings.json entry missing %r: %r" % (k, h))
        if h["sector"] not in SECTORS:
            fail("holdings.json %s sector must be one of %s" % (h["ticker"], SECTORS))
    if not isinstance(status.get("takes", {}), dict):
        fail("status.json takes must be an object keyed by ticker")
    for t, v in status.get("takes", {}).items():
        if v.get("take") not in TAKES:
            fail("status.json take for %s must be one of %s" % (t, TAKES))
    for where_, figure in holding_price_leaks(holdings, status.get("takes", {}), news):
        fail("%s quotes a holding share price (%s); use %% moves, never prices" % (where_, figure))
    seen = set()
    for w in watchlist:
        for k in ("ticker", "exchange", "name", "sector", "status", "conviction", "thesis", "risks", "added", "updated"):
            if k not in w:
                fail("watchlist.json %s missing %r" % (w.get("ticker"), k))
        if w["sector"] not in SECTORS:
            fail("watchlist.json %s sector must be one of %s" % (w["ticker"], SECTORS))
        if w["status"] not in STATUSES:
            fail("watchlist.json %s status must be one of %s" % (w["ticker"], STATUSES))
        if w["conviction"] not in CONVICTIONS:
            fail("watchlist.json %s conviction must be one of %s" % (w["ticker"], CONVICTIONS))
        key = (w["ticker"], w["exchange"])
        if key in seen:
            fail("watchlist.json duplicate %s:%s" % key)
        seen.add(key)
    for n in news:
        for k in ("date", "ticker", "headline", "summary", "source", "impact"):
            if k not in n:
                fail("news.json item missing %r: %r" % (k, n))
        if n["impact"] not in IMPACTS:
            fail("news.json %s impact must be one of %s" % (n["ticker"], IMPACTS))
        try:
            datetime.strptime(n["date"], "%Y-%m-%d")
        except ValueError:
            fail("news.json bad date %r" % n["date"])


# ------------------------------------------------------------------ sections
# (anchor, directory, nav label, page title). Every section has its own page; the
# landing page carries a short summary of each with a link through.
PAGES = [
    ("build", "builds", "what i build", "What I build"),
    ("take", "take", "agent's take", "Agent's take"),
    ("portfolio", "portfolio", "portfolio", "Portfolio (what I'm invested in)"),
    ("picks", "picks", "agent picks", "Agent picks (researching for future growth)"),
    ("bellwethers", "bellwethers", "ai bellwethers", "AI bubble bellwethers (is compute being sold at a discount?)"),
    ("calendar", "calendar", "next fortnight", "Next fortnight (what to watch or listen to)"),
    ("love", "love", "companies i love", "Companies I love"),
    ("gear", "buys", "gear i'm hunting", "Gear I'm hunting"),
    ("news", "news", "news", "News"),
    ("research", "research", "research log", "Research log"),
]
SUMMARY_DAYS = 3
SUMMARY_NEWS = 6
SUMMARY_LOGS = 3


def section(anchor, summary, more=None):
    _, d, _, title = next(p for p in PAGES if p[0] == anchor)
    out = '<h2 id="%s"><a href="%s/">%s</a></h2>\n%s' % (anchor, d, e(title), summary)
    return out + '<p><a href="%s/">%s &rarr;</a></p>\n' % (d, e(more or "more"))


def render_header(profile):
    links = " | ".join(link(l["url"], l["label"]) for l in profile.get("links", []))
    return (
        "<h1>%s</h1>\n<p>%s</p>\n<p>%s</p>\n"
        % (e(profile["name"]), e(profile.get("tagline")), links)
        + "<p>%s</p>\n" % e(profile.get("bio"))
    )


def render_nav(prefix="", current=None):
    items = []
    for _, d, label, _ in PAGES:
        items.append("<b>%s</b>" % e(label) if d == current else '<a href="%s%s/">%s</a>' % (prefix, d, e(label)))
    return "<p>" + " | ".join(items) + "</p>\n"


def subpage_head(d, title):
    return ('<p><a href="../">&larr; home</a></p>\n' + render_nav("../", d)
            + "<hr>\n<h1>%s</h1>\n" % e(title))


# ----------------------------------------------------------- landing summaries
def site_label(url):
    return url.split("://", 1)[-1].rstrip("/") if url else ""


def summary_builds(profile):
    out = "<ul>\n"
    for b in profile.get("builds", []):
        out += "<li><b>%s</b> &mdash; %s" % (e(b["name"]), e(b.get("role")))
        if b.get("short"):
            out += "<br>%s" % e(b["short"])
        if b.get("url"):
            out += "<br>%s" % link(b["url"], site_label(b["url"]))
        out += "</li>\n"
    return out + "</ul>\n"


def summary_take(status):
    out = "<p><i>last updated: %s (UTC)</i></p>\n" % e(status.get("as_of") or "never")
    if status.get("headlines"):
        out += "<ul>\n" + "".join("<li>%s</li>\n" % e(h) for h in status["headlines"]) + "</ul>\n"
    elif status.get("market_summary"):
        out += "<p>%s</p>\n" % e(status["market_summary"])
    return out


def summary_portfolio(holdings, status):
    # Weights and takes only, grouped by take.
    takes = status.get("takes", {})
    w = weights(holdings, status)
    out = "<ul>\n"
    for take in ("add", "hold", "trim", "watch"):
        group = sorted([h for h in holdings if takes.get(h["ticker"], {}).get("take") == take],
                       key=lambda h: -w.get(h["ticker"], 0))
        if group:
            out += "<li><b>%s</b>: %s</li>\n" % (e(take), ", ".join(
                "%s %s" % (e(h["ticker"]), fmt_weight(w, h["ticker"])) for h in group))
    return out + "</ul>\n"


def summary_watchlist(watchlist):
    if not watchlist:
        return "<p>No picks yet.</p>\n"
    conv = {c: i for i, c in enumerate(CONVICTIONS)}
    out = "<ul>\n"
    for status in STATUSES:
        group = sorted([w for w in watchlist if w["status"] == status],
                       key=lambda w: (conv.get(w["conviction"], 9), w["ticker"]))
        if group:
            out += "<li><b>%s</b>: %s</li>\n" % (e(status), ", ".join(
                "%s (%s)" % (e(w["ticker"]), e(w["name"])) for w in group))
    return out + "</ul>\n"


def summary_indicators(ind):
    items = ind.get("indicators", [])
    if not items:
        return "<p>No indicator data yet.</p>\n"
    counts = [(s, len([i for i in items if i["signal"] == s])) for s in SIGNALS]
    out = "<p>%s</p>\n<ul>\n" % ", ".join("%d %s" % (n, s) for s, n in counts if n)
    for i in items:
        out += "<li><b>%s</b> (%s) &mdash; %s</li>\n" % (
            e(i["signal"]), e(i["trend"]), e(i["name"].split(" (")[0].split(":")[0]))
    return out + "</ul>\n"


def summary_calendar(cal, today):
    start = today.strftime("%Y-%m-%d")
    end = (today + timedelta(days=SUMMARY_DAYS - 1)).strftime("%Y-%m-%d")
    events = sorted([ev for ev in cal.get("events", []) if start <= ev["date"] <= end],
                    key=lambda ev: (ev["date"], ev["ticker"]))
    if not events:
        return "<p>Nothing on file for the next %d days.</p>\n" % SUMMARY_DAYS
    out = "<ul>\n"
    for ev in events:
        day = datetime.strptime(ev["date"], "%Y-%m-%d").strftime("%a %d %b")
        out += "<li>%s: <b>%s</b> %s</li>\n" % (e(day), e(ev["ticker"]), e(ev["title"]))
    return out + "</ul>\n"


def summary_loves(loves):
    return "<p>%s</p>\n" % ", ".join(e(l["name"]) for l in loves)


def summary_news(news):
    if not news:
        return "<p>No news yet.</p>\n"
    items = sorted(news, key=lambda n: n["date"], reverse=True)[:SUMMARY_NEWS]
    return "<ul>\n" + "".join("<li>[%s] <b>%s</b> %s</li>\n" % (
        {"positive": "+", "negative": "-", "neutral": "n"}[n["impact"]], e(n["ticker"]), e(n["headline"]))
        for n in items) + "</ul>\n"


def summary_research(logs):
    if not logs:
        return "<p>No research logs yet.</p>\n"
    return "<ul>\n" + "".join("<li>%s</li>\n" % link("research/%s.html" % n[:-3], n[:-3])
                              for n in logs[:SUMMARY_LOGS]) + "</ul>\n"


def render_builds(profile):
    out = "<ul>\n"
    for b in profile.get("builds", []):
        name = link(b.get("url"), b["name"]) if b.get("url") else "<b>%s</b>" % e(b["name"])
        out += "<li>%s &mdash; %s<br>%s</li>\n" % (name, e(b.get("role")), e(b.get("why")))
    return out + "</ul>\n"


def render_take(status):
    as_of = status.get("as_of") or "never"
    summary = status.get("market_summary") or "No research run yet."
    out = "<p><i>last updated: %s (UTC)</i></p>\n" % e(as_of)
    if status.get("headlines"):
        out += "<p><b>What changed since the last run</b></p>\n<ul>\n" + "".join(
            "<li>%s</li>\n" % e(h) for h in status["headlines"]) + "</ul>\n"
    out += "<p>%s</p>\n" % e(summary)
    return out


def weights(holdings, status):
    """Share of portfolio by estimated value, 0-100, keyed by ticker. Never rendered as dollars."""
    takes = status.get("takes", {})
    values = {}
    for h in holdings:
        t = takes.get(h["ticker"], {})
        price = t.get("price_usd")
        if price is not None and h.get("units"):
            values[h["ticker"]] = float(price) * float(h["units"])
        elif h.get("cost_usd"):
            # private: cost basis x latest valuation mark (1.0 if the agent has not marked it yet)
            values[h["ticker"]] = float(h["cost_usd"]) * float(t.get("mark_multiple") or 1.0)
    total = sum(values.values())
    return {k: 100.0 * v / total for k, v in values.items()} if total else {}


def fmt_weight(w, ticker):
    return ("%.1f%%" % w[ticker]) if ticker in w else "-"


def render_portfolio(holdings, status):
    # Shows allocation weight only (no units, prices or dollar values).
    takes = status.get("takes", {})
    w = weights(holdings, status)
    rows = []
    for h in holdings:
        t = takes.get(h["ticker"], {})
        weight = fmt_weight(w, h["ticker"])
        rows.append(
            '<tr><td><b>%s</b>:%s</td><td data-label="weight" class="nw">%s</td><td data-label="take">%s</td></tr>'
            % (
                e(h["ticker"]), e(h["exchange"]), weight,
                ("<b>%s</b> &mdash; %s" % (e(t.get("take")), e(t.get("reason")))) if t else "-",
            )
        )
    out = (
        '<table border="1" cellpadding="4" cellspacing="0">\n'
        "<tr><th>ticker</th><th>weight</th><th>agent take</th></tr>\n"
        + "\n".join(rows)
        + "\n</table>\n"
    )
    if w:
        out += "<p><i>weight = share of portfolio by estimated value: public holdings at last research-run prices, private holdings at cost marked to the latest reported valuation.</i></p>\n"
    return out


def render_watchlist(watchlist):
    if not watchlist:
        return "<p>No picks yet.</p>\n"
    order = {s: i for i, s in enumerate(STATUSES)}
    conv = {c: i for i, c in enumerate(CONVICTIONS)}
    items = sorted(watchlist, key=lambda w: (order.get(w["status"], 9), conv.get(w["conviction"], 9), w["ticker"]))
    out = ""
    for sector in SECTORS:
        group = [w for w in items if w["sector"] == sector]
        if not group:
            continue
        out += "<h3>%s</h3>\n<ul>\n" % e(sector)
        for w in group:
            out += (
                "<li><b>%s</b>:%s %s &mdash; <b>%s</b> (%s conviction)%s<br>"
                "thesis: %s<br>risks: %s<br>%s<i>added %s, updated %s</i>%s</li>\n"
                % (
                    e(w["ticker"]), e(w["exchange"]), e(w["name"]), e(w["status"]), e(w["conviction"]),
                    (" &mdash; %s" % money(w.get("price_usd"))) if w.get("price_usd") is not None else "",
                    e(w["thesis"]), e(w["risks"]),
                    ("catalyst: %s<br>" % e(w["catalyst"])) if w.get("catalyst") else "",
                    e(w["added"]), e(w["updated"]),
                    (" &mdash; %s" % link(w["source"], "source")) if w.get("source") else "",
                )
            )
        out += "</ul>\n"
    return out


def render_calendar(cal, today):
    start = today.strftime("%Y-%m-%d")
    end = (today + timedelta(days=CALENDAR_DAYS)).strftime("%Y-%m-%d")
    events = sorted([ev for ev in cal.get("events", []) if start <= ev["date"] <= end],
                    key=lambda ev: (ev["date"], ev["ticker"]))
    if not events:
        return "<p>No events on file for %s to %s.</p>\n" % (start, end)
    out = "<p><i>%s to %s (UTC dates). Times as published by the source.</i></p>\n" % (e(start), e(end))
    current = None
    for ev in events:
        if ev["date"] != current:
            if current is not None:
                out += "</ul>\n"
            current = ev["date"]
            day = datetime.strptime(current, "%Y-%m-%d").strftime("%a %Y-%m-%d")
            out += "<h3>%s</h3>\n<ul>\n" % e(day)
        title = link(ev["link"], ev["title"]) if ev.get("link") else e(ev["title"])
        out += "<li>[%s] <b>%s</b> %s (%s) &mdash; %s</li>\n" % (
            e(ev["type"]), e(ev["ticker"]), title, e(ev["time"]), e(ev["why"]))
    out += "</ul>\n"
    return out


def render_indicators(ind):
    items = ind.get("indicators", [])
    if not items:
        return "<p>No indicator data yet.</p>\n"
    out = ""
    if ind.get("explainer"):
        out += "<p>%s</p>\n" % e(ind["explainer"])
    out += (
        '<table border="1" cellpadding="4" cellspacing="0">\n'
        "<tr><th>indicator</th><th>reading</th><th>trend</th><th>signal</th><th>why it matters / what to watch</th></tr>\n"
    )
    for i in items:
        out += '<tr><td><b>%s</b><br><i>%s</i></td><td data-label="reading">%s</td><td data-label="trend" class="nw">%s</td><td data-label="signal" class="nw"><b>%s</b></td><td data-label="why">%s<br>watch: %s%s</td></tr>\n' % (
            e(i["name"]), e(i["updated"]), e(i["value"]), e(i["trend"]), e(i["signal"]),
            e(i["why"]), e(i["watch"]),
            (" &mdash; %s" % link(i["source"], "source")) if i.get("source") else "")
    out += "</table>\n<p><i>signal is from the AI-infrastructure investor's view: bullish = still supply-constrained, bearish = compute being discounted / oversupplied.</i></p>\n"
    return out


def render_loves(loves):
    out = "<ul>\n"
    for l in loves:
        t = (" (%s)" % e(l["ticker"])) if l.get("ticker") else " (private)"
        out += "<li><b>%s</b>%s &mdash; %s</li>\n" % (e(l["name"]), t, e(l.get("why")))
    return out + "</ul>\n"


def render_news(news):
    if not news:
        return "<p>No news yet.</p>\n"
    items = sorted(news, key=lambda n: n["date"], reverse=True)[:MAX_NEWS_ON_PAGE]
    out = ""
    current = None
    for n in items:
        if n["date"] != current:
            if current is not None:
                out += "</ul>\n"
            current = n["date"]
            out += "<h3>%s</h3>\n<ul>\n" % e(current)
        out += "<li>[%s] <b>%s</b> %s &mdash; %s %s</li>\n" % (
            {"positive": "+", "negative": "-", "neutral": "n"}[n["impact"]], e(n["ticker"]), e(n["headline"]), e(n["summary"]), link(n["source"], "source"))
    out += "</ul>\n<p><i>[+] positive, [-] negative, [n] neutral</i></p>\n"
    return out


# --------------------------------------------------------------- the buy list
def live_for(finds, key):
    return [f for f in finds if f.get("want") == key and f.get("status", "live") == "live"]


def gone_for(finds, key):
    return [f for f in finds if f.get("want") == key and f.get("status", "live") != "live"]


def find_price(f):
    out = aud(f.get("price_aud"))
    if f.get("price_note"):
        out += " (%s)" % e(f["price_note"])
    return out


def find_place(f):
    out = e(f.get("location") or "location TBC")
    if f.get("distance_km") is not None:
        out += " (%skm)" % e(f["distance_km"])
    return out


def find_oneline(f):
    # Landing page: bare price only. The note and the full detail live on /buys.
    bits = [aud(f.get("price_aud"))]
    if f.get("detail"):
        bits.append(e(f["detail"][0]))
    bits.append(find_place(f))
    return "%s &mdash; %s" % (link(f.get("url"), f.get("title")), " &middot; ".join(bits))


def render_gear(wants, finds):
    """Landing-page summary: one line per category, best find only."""
    items = [w for w in wants.get("wants", []) if w.get("status") != "done"]
    if not items:
        return "<p>Nothing on the list right now.</p>\n"
    all_finds = finds.get("finds", [])
    out = ""
    if finds.get("as_of"):
        out += "<p><i>last checked: %s (UTC)</i></p>\n" % e(finds["as_of"])
    if finds.get("headlines"):
        out += "<ul>\n" + "".join("<li>%s</li>\n" % e(h) for h in finds["headlines"]) + "</ul>\n"
    out += "<ul>\n"
    for w in items:
        live = live_for(all_finds, w["key"])
        head = "<b>%s</b> &mdash; %s" % (
            e(w["short"]), ("%d live" % len(live)) if live else "no finds yet")
        if w.get("status") == "paused":
            head += " (paused)"
        out += "<li>%s" % head
        if live:
            out += "<br>best: %s" % find_oneline(live[0])
        out += "</li>\n"
    return out + "</ul>\n"


def render_find(f, prefix=""):
    out = "<li>"
    if f.get("photo"):
        out += '<a href="%s"><img src="%s%s" alt="%s" width="320"></a><br>' % (
            e(f.get("url")), e(prefix), e(f["photo"]), e(f.get("title")))
    out += "<b>%s</b>" % link(f.get("url"), f.get("title"))
    if f.get("verdict"):
        out += " &mdash; %s" % e(f["verdict"])
    if f.get("status", "live") != "live":
        out += " [%s]" % e(f["status"])
    out += "<br>%s &middot; %s" % (find_price(f), find_place(f))
    if f.get("detail"):
        out += "<br>%s" % " &middot; ".join(e(d) for d in f["detail"])
    if f.get("why"):
        out += "<br>%s" % e(f["why"])
    tail = [e(f.get("source"))]
    if f.get("ends"):
        tail.append("ends %s" % e(f["ends"]))
    if f.get("first_seen"):
        tail.append("first seen %s" % e(f["first_seen"]))
    out += "<br><i>%s</i></li>\n" % " &middot; ".join(t for t in tail if t)
    return out


def render_buys(wants, finds, logs):
    bases = wants.get("bases", {})
    all_finds = finds.get("finds", [])
    out = subpage_head("buys", "Gear I'm hunting")
    if finds.get("as_of"):
        out += "<p><i>last checked: %s (UTC)</i></p>\n" % e(finds["as_of"])
    if finds.get("summary"):
        out += "<p>%s</p>\n" % e(finds["summary"])
    for w in wants.get("wants", []):
        if w.get("status") == "done":
            continue
        live, gone = live_for(all_finds, w["key"]), gone_for(all_finds, w["key"])
        out += '<h2 id="%s">%s%s</h2>\n' % (
            e(w["key"]), e(w["title"]), " (paused)" if w.get("status") == "paused" else "")
        out += "<p>%s &middot; %s</p>\n" % (band(w), where(w, bases))
        if w.get("must"):
            out += "<p>must have: %s</p>\n" % "; ".join(e(m) for m in w["must"])
        if w.get("prefer"):
            out += "<p>nice to have: %s</p>\n" % "; ".join(e(p) for p in w["prefer"])
        if w.get("notes"):
            out += "<p><i>%s</i></p>\n" % e(w["notes"])
        if live:
            out += "<ul>\n" + "".join(render_find(f, "../") for f in live) + "</ul>\n"
        else:
            out += "<p>Nothing worth a look yet.</p>\n"
        if gone:
            out += "<p><i>recently gone: %s</i></p>\n" % "; ".join(
                "%s at %s (%s)" % (e(f.get("title")), find_price(f), e(f.get("status"))) for f in gone)
    done = [w for w in wants.get("wants", []) if w.get("status") == "done"]
    if done:
        out += "<h2>Sorted</h2>\n<ul>\n" + "".join(
            "<li>%s%s</li>\n" % (e(w["title"]), (" &mdash; %s" % e(w["got"])) if w.get("got") else "")
            for w in done) + "</ul>\n"
    out += "<h2>Hunt log</h2>\n"
    if logs:
        out += "<ul>\n" + "".join(
            "<li>%s</li>\n" % link("../hunt/%s.html" % n[:-3], n[:-3]) for n in logs[:14]) + "</ul>\n"
        if len(logs) > 14:
            out += "<p>%s</p>\n" % link("../hunt/", "all %d runs" % len(logs))
    else:
        out += "<p>No hunt runs yet.</p>\n"
    out += ("<p><i>Prices are what the seller or auction house is asking, before premium, "
            "transport or GST unless noted. Verify everything before you commit money.</i></p>\n")
    return out


def research_logs():
    files = sorted(glob.glob(os.path.join(RESEARCH, "*.md")), reverse=True)
    return [os.path.basename(f) for f in files]


def hunt_logs_list():
    files = sorted(glob.glob(os.path.join(HUNT, "*.md")), reverse=True)
    return [os.path.basename(f) for f in files]


def render_research(logs):
    if not logs:
        return "<p>No research logs yet.</p>\n"
    return "<ul>\n" + "".join(
        "<li>%s</li>\n" % link("%s.html" % n[:-3], n[:-3]) for n in logs) + "</ul>\n"


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<link rel="icon" href="data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%%3E%%3Ctext y='.9em' font-size='90'%%3E%%F0%%9F%%A7%%91%%E2%%80%%8D%%F0%%9F%%92%%BB%%3C/text%%3E%%3C/svg%%3E">
<link rel="icon" type="image/png" sizes="64x64" href="/favicon.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<style>
body{font-family:Verdana,Geneva,sans-serif;font-size:15px;line-height:1.45;max-width:960px;margin:1em auto;padding:0 0.8em;color:#000;background:#fff;-webkit-text-size-adjust:100%%}
a{color:#00e;word-break:break-word}a:visited{color:#551a8b}
table{border-collapse:collapse;font-size:14px;width:100%%}th{text-align:left}td,th{vertical-align:top}td.nw{white-space:nowrap}
ul{padding-left:1.2em}li{margin-bottom:0.4em}
img{max-width:100%%;height:auto;border:1px solid #ccc;margin:0.3em 0}
pre{white-space:pre-wrap;word-wrap:break-word}
h1,h2,h3{font-weight:bold}h1{font-size:20px}h2{font-size:17px;margin-top:2em}h3{font-size:15px}
@media (max-width:600px){table,thead,tbody,tr,td,th{display:block;width:auto}tr{border-bottom:2px solid #000;padding:0.4em 0}td,th{border:0!important;padding:0.1em 0}th{display:none}td.nw{white-space:normal}td[data-label]::before{content:attr(data-label) ": ";color:#555}}
</style>
</head>
<body>
%(body)s
<hr>
<p><i>Nothing here is financial advice. Holdings and opinions are my own; the "agent" sections are written by an automated research skill and may be wrong. Built %(built)s UTC.</i></p>
</body>
</html>
"""


def build():
    profile = load("profile.json")
    holdings = load("holdings.json")
    loves = load("loves.json")
    status = load("status.json")
    watchlist = load("watchlist.json")
    news = load("news.json")
    indicators = load("indicators.json")
    calendar = load("calendar.json")
    wants = load("wants.json")
    finds = load("finds.json")
    validate(profile, holdings, loves, status, watchlist, news, indicators, calendar, wants, finds)
    if "--check" in sys.argv:
        live = len([f for f in finds.get("finds", []) if f.get("status", "live") == "live"])
        print("data ok: %d holdings, %d picks, %d news items, %d wants, %d live finds"
              % (len(holdings), len(watchlist), len(news), len(wants.get("wants", [])), live))
        return

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    logs = research_logs()
    hunt_logs = hunt_logs_list()
    now = datetime.now(timezone.utc)
    live = len([f for f in finds.get("finds", []) if f.get("status", "live") == "live"])

    # landing page: every section as a short summary, linking to its own page
    body = render_header(profile) + render_nav() + "<hr>\n"
    body += section("build", summary_builds(profile))
    body += section("take", summary_take(status), "market summary")
    body += section("portfolio", summary_portfolio(holdings, status), "takes and reasons")
    body += section("picks", summary_watchlist(watchlist), "theses, risks and catalysts")
    body += section("bellwethers", summary_indicators(indicators), "readings and what to watch")
    body += section("calendar", summary_calendar(calendar, now), "full %d days" % CALENDAR_DAYS)
    body += section("love", summary_loves(loves), "why")
    body += section("gear", render_gear(wants, finds), "all %d finds, with photos and detail" % live)
    body += section("news", summary_news(news), "all news")
    body += section("research", summary_research(logs), "all %d logs" % len(logs))
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE % {"title": profile["name"], "body": body, "built": built})

    # one page per section
    full = {
        "build": render_builds(profile),
        "take": render_take(status),
        "portfolio": render_portfolio(holdings, status),
        "picks": render_watchlist(watchlist),
        "bellwethers": render_indicators(indicators),
        "calendar": render_calendar(calendar, now),
        "love": render_loves(loves),
        "gear": render_buys(wants, finds, hunt_logs),
        "news": render_news(news),
        "research": render_research(logs),
    }
    for anchor, d, label, title in PAGES:
        page = full[anchor] if anchor == "gear" else subpage_head(d, title) + full[anchor]
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
        with open(os.path.join(ROOT, d, "index.html"), "w", encoding="utf-8") as f:
            f.write(PAGE % {"title": "%s - %s" % (profile["name"], label), "body": page, "built": built})

    # research/*.md -> research/*.html as plain text
    for name in logs:
        with open(os.path.join(RESEARCH, name), encoding="utf-8") as f:
            text = f.read()
        page_body = '<p><a href="./">&larr; research log</a></p>\n<pre>%s</pre>\n' % e(text)
        with open(os.path.join(RESEARCH, name[:-3] + ".html"), "w", encoding="utf-8") as f:
            f.write(PAGE % {"title": "%s - %s" % (profile["name"], name[:-3]), "body": page_body, "built": built})

    # hunt/*.md -> hunt/*.html, same treatment as the research log
    if hunt_logs:
        for name in hunt_logs:
            with open(os.path.join(HUNT, name), encoding="utf-8") as f:
                text = f.read()
            page_body = '<p><a href="../buys/">&larr; gear</a></p>\n<pre>%s</pre>\n' % e(text)
            with open(os.path.join(HUNT, name[:-3] + ".html"), "w", encoding="utf-8") as f:
                f.write(PAGE % {"title": "%s - hunt %s" % (profile["name"], name[:-3]),
                                "body": page_body, "built": built})
        hidx = '<p><a href="../buys/">&larr; gear</a></p>\n<h1>Hunt log</h1>\n<ul>\n' + "".join(
            "<li>%s</li>\n" % link("%s.html" % n[:-3], n[:-3]) for n in hunt_logs) + "</ul>\n"
        with open(os.path.join(HUNT, "index.html"), "w", encoding="utf-8") as f:
            f.write(PAGE % {"title": "%s - hunt log" % profile["name"], "body": hidx, "built": built})

    print("built index.html + %d section pages + %d research pages + %d hunt pages" % (len(PAGES), len(logs), len(hunt_logs)))


if __name__ == "__main__":
    build()
