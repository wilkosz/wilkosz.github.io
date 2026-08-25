#!/usr/bin/env python3
"""Build wilkosz.com.au from data/*.json + research/*.md.

Text-only, no dependencies beyond the Python stdlib.

    python3 build.py          # writes index.html and research/*.html
    python3 build.py --check  # validate data files only, no output

Owner-maintained:  data/profile.json  data/holdings.json  data/loves.json
Agent-maintained:  data/status.json   data/watchlist.json data/news.json  research/*.md
"""
import glob
import html
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RESEARCH = os.path.join(ROOT, "research")

SECTORS = ("AI", "Internet", "Machinery", "Energy")
TAKES = ("hold", "add", "trim", "watch")
STATUSES = ("buy", "accumulate", "watch", "avoid")
CONVICTIONS = ("high", "medium", "low")
IMPACTS = ("positive", "negative", "neutral")
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


# ---------------------------------------------------------------- validation
def fail(msg):
    print("INVALID: " + msg, file=sys.stderr)
    sys.exit(1)


def validate(profile, holdings, loves, status, watchlist, news):
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
def section(title, body, anchor):
    return '<h2 id="%s">%s</h2>\n%s\n' % (anchor, e(title), body)


def render_header(profile):
    links = " | ".join(link(l["url"], l["label"]) for l in profile.get("links", []))
    return (
        "<h1>%s</h1>\n<p>%s</p>\n<p>%s</p>\n"
        % (e(profile["name"]), e(profile.get("tagline")), links)
        + "<p>%s</p>\n" % e(profile.get("bio"))
    )


def render_nav():
    items = [
        ("#build", "what i build"),
        ("#take", "agent's take"),
        ("#portfolio", "portfolio"),
        ("#picks", "agent picks"),
        ("#love", "companies i love"),
        ("#news", "news"),
        ("#research", "research log"),
    ]
    return "<p>" + " | ".join('<a href="%s">%s</a>' % (a, t) for a, t in items) + "</p>\n"


def render_builds(profile):
    out = "<ul>\n"
    for b in profile.get("builds", []):
        name = link(b.get("url"), b["name"]) if b.get("url") else "<b>%s</b>" % e(b["name"])
        out += "<li>%s &mdash; %s<br>%s</li>\n" % (name, e(b.get("role")), e(b.get("why")))
    return out + "</ul>\n"


def render_take(status):
    as_of = status.get("as_of") or "never"
    summary = status.get("market_summary") or "No research run yet."
    return "<p><i>last updated: %s (UTC)</i></p>\n<p>%s</p>\n" % (e(as_of), e(summary))


def render_portfolio(holdings, status):
    # Shows allocation weight only (no units, prices or dollar values).
    takes = status.get("takes", {})
    values = {}
    for h in holdings:
        price = takes.get(h["ticker"], {}).get("price_usd")
        if price is not None and h.get("units"):
            values[h["ticker"]] = float(price) * float(h["units"])
    total = sum(values.values())
    rows = []
    for h in holdings:
        t = takes.get(h["ticker"], {})
        v = values.get(h["ticker"])
        weight = ("%.1f%%" % (100.0 * v / total)) if (v is not None and total) else "-"
        rows.append(
            "<tr><td><b>%s</b>:%s</td><td>%s</td><td>%s</td></tr>"
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
    if total:
        out += "<p><i>weight = share of public holdings by market value at last research-run prices; private holdings unpriced.</i></p>\n"
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


def research_logs():
    files = sorted(glob.glob(os.path.join(RESEARCH, "*.md")), reverse=True)
    return [os.path.basename(f) for f in files]


def render_research(logs):
    if not logs:
        return "<p>No research logs yet.</p>\n"
    out = "<ul>\n"
    for name in logs[:30]:
        out += "<li>%s</li>\n" % link("research/%s.html" % name[:-3], name[:-3])
    out += "</ul>\n"
    if len(logs) > 30:
        out += "<p>%s</p>\n" % link("research/", "all %d logs" % len(logs))
    return out


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
body{font-family:Verdana,Geneva,sans-serif;font-size:14px;line-height:1.4;max-width:960px;margin:1em auto;padding:0 1em;color:#000;background:#fff}
a{color:#00e}a:visited{color:#551a8b}
table{border-collapse:collapse;font-size:13px}th{text-align:left}
pre{white-space:pre-wrap;word-wrap:break-word}
h1,h2,h3{font-weight:bold}h1{font-size:20px}h2{font-size:16px;margin-top:2em}h3{font-size:14px}
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
    validate(profile, holdings, loves, status, watchlist, news)
    if "--check" in sys.argv:
        print("data ok: %d holdings, %d picks, %d news items" % (len(holdings), len(watchlist), len(news)))
        return

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    logs = research_logs()
    body = render_header(profile) + render_nav() + "<hr>\n"
    body += section("What I build", render_builds(profile), "build")
    body += section("Agent's take", render_take(status), "take")
    body += section("Portfolio (what I'm invested in)", render_portfolio(holdings, status), "portfolio")
    body += section("Agent picks (researching for future growth)", render_watchlist(watchlist), "picks")
    body += section("Companies I love", render_loves(loves), "love")
    body += section("News", render_news(news), "news")
    body += section("Research log", render_research(logs), "research")

    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE % {"title": profile["name"], "body": body, "built": built})

    # research/*.md -> research/*.html as plain text, plus an index
    os.makedirs(RESEARCH, exist_ok=True)
    for name in logs:
        with open(os.path.join(RESEARCH, name), encoding="utf-8") as f:
            text = f.read()
        page_body = '<p><a href="../">&larr; home</a></p>\n<pre>%s</pre>\n' % e(text)
        with open(os.path.join(RESEARCH, name[:-3] + ".html"), "w", encoding="utf-8") as f:
            f.write(PAGE % {"title": "%s - %s" % (profile["name"], name[:-3]), "body": page_body, "built": built})
    idx = '<p><a href="../">&larr; home</a></p>\n<h1>Research log</h1>\n<ul>\n' + "".join(
        "<li>%s</li>\n" % link("%s.html" % n[:-3], n[:-3]) for n in logs) + "</ul>\n"
    with open(os.path.join(RESEARCH, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE % {"title": "%s - research" % profile["name"], "body": idx, "built": built})
    print("built index.html + %d research pages" % len(logs))


if __name__ == "__main__":
    build()
