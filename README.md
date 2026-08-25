# wilkosz.com.au

Text-only personal site for Joshua Wilkosz, served by GitHub Pages from `index.html`.
Half of the page is written by me, half by an automated market-research skill.

## Layout

```
index.html            generated - do not edit by hand
build.py              renders index.html + research/*.html from data/ (stdlib only)
merge.py              merges one research run JSON into data/, writes research/<stamp>.md, rebuilds
data/profile.json     who I am, what I build            (owner-maintained)
data/holdings.json    what I'm invested in              (owner-maintained)
data/loves.json       companies I love                  (owner-maintained)
data/status.json      agent's take + per-holding takes  (agent-maintained)
data/watchlist.json   agent picks                       (agent-maintained)
data/news.json        recent news, deduped by URL       (agent-maintained)
data/indicators.json  AI-bubble bellwether readings     (agent-maintained)
data/calendar.json    next-fortnight events             (agent-maintained)
research/*.md         one log per research run          (agent-maintained)
.claude/skills/market-research/SKILL.md   the research procedure
.claude/settings.json                     bypassPermissions for this repo
```

## Running the research loop

From this directory in Claude Code:

```
/market-research                 # one run: research, merge, build, commit, push
/loop 6h /market-research        # keep the session open and re-run every 6 hours
```

Skills are discovered when a session starts, so run these from a fresh session (or use the
long-form prompt: "read .claude/skills/market-research/SKILL.md and follow it").

Instructions after the command are treated as owner instructions for that run,
e.g. `/market-research add 10 units of NVDA` or `/market-research focus on nuclear this run`.

## Editing my own sections

Edit `data/profile.json`, `data/holdings.json` or `data/loves.json`, then:

```
python3 build.py && git commit -am "update holdings" && git push
```

`python3 build.py --check` validates the data files without writing anything.
