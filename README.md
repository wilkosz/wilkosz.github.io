# wilkosz.com.au

Mostly-text personal site for Joshua Wilkosz, served by GitHub Pages from `index.html`.
Half of the page is written by me, half by two automated agent loops: market research, and
a daily hunt for second-hand farm gear.

## Layout

```
index.html            generated - do not edit by hand
buys/index.html       generated - the full buy list, with photos
build.py              renders index.html + buys/ + research/ + hunt/ from data/ (stdlib only)
merge.py              merges one research run JSON into data/, writes research/<stamp>.md, rebuilds
hunt.py               merges one asset-hunt run JSON into data/, fetches photos, writes hunt/<stamp>.md, rebuilds
data/profile.json     who I am, what I build            (owner-maintained)
data/holdings.json    what I'm invested in              (owner-maintained)
data/loves.json       companies I love                  (owner-maintained)
data/wants.json       gear I'm hunting, and the specs   (owner-maintained)
data/status.json      agent's take + per-holding takes  (agent-maintained)
data/watchlist.json   agent picks                       (agent-maintained)
data/news.json        recent news, deduped by URL       (agent-maintained)
data/indicators.json  AI-bubble bellwether readings     (agent-maintained)
data/calendar.json    next-fortnight events             (agent-maintained)
data/finds.json       live listings against each want   (agent-maintained)
img/finds/*.jpg       one 400px thumbnail per find      (agent-maintained)
research/*.md         one log per research run          (agent-maintained)
hunt/*.md             one log per asset-hunt run        (agent-maintained)
.claude/skills/market-research/SKILL.md   the research procedure
.claude/skills/asset-hunt/SKILL.md        the buying procedure
.claude/settings.json                     bypassPermissions for this repo
```

## Running the loops

From this directory in Claude Code:

```
/market-research                 # one run: research, merge, build, commit, push
/loop 6h /market-research        # re-run every 6 hours

/asset-hunt                      # one run: sweep the market, merge, build, commit, push
/loop 24h /asset-hunt            # re-run daily
```

Both commit and push to `main` on their own - they don't stop to ask, because they run
unattended and the site is only useful once it's live.

Skills are discovered when a session starts, so run these from a fresh session (or use the
long-form prompt: "read .claude/skills/asset-hunt/SKILL.md and follow it").

Instructions after the command are treated as owner instructions for that run,
e.g. `/market-research add 10 units of NVDA`, or `/asset-hunt add a post hole digger,
3PL, under $4k` and `/asset-hunt got the chainsaw - MS 462 for $1,400`.

Facebook Marketplace is only reachable through a logged-in Chrome session with the Claude
extension connected. If it isn't available, `/asset-hunt` logs "Facebook skipped" and
publishes the auction and dealer results anyway.

## Editing my own sections

Edit `data/profile.json`, `data/holdings.json`, `data/loves.json` or `data/wants.json`, then:

```
python3 build.py && git commit -am "update holdings" && git push
```

`python3 build.py --check` validates the data files without writing anything.
