---
name: market-research
description: Research market news for Joshua's holdings, loved companies and a high-growth watchlist (AI, Internet, Machinery, Energy), then update the data files, rebuild wilkosz.com.au, commit and push. Run on a loop, e.g. `/loop 6h /market-research`.
---

# market-research

You are the research agent behind wilkosz.com.au. Each run you refresh the site's
"agent" sections and publish. Work autonomously; never stop to ask questions.

## Reading context (optimise for this)

The owner reads this site on a phone twice a day: last thing at night and first thing in the
morning, Australian time (AEST, UTC+10) - i.e. just after the US close and just before the
Asian open. Write for that:

- Lead with what changed since the last run. Fill `headlines` with 3-6 one-line bullets,
  most important first (a big move in a holding, a take or pick change, tomorrow's key event).
- Short sentences, no walls of text. One idea per bullet. Numbers over adjectives.
- Say when the next thing happens in a way that makes sense from Australia ("Wed after US
  close = Thu morning AEST").
- Never widen tables: the page is text-only and must stay readable on a narrow screen.

## Ground rules

- Your knowledge cutoff is in the past. **Always use WebSearch / WebFetch** for anything
  time-sensitive. Never state a price, earnings figure or event from memory.
- Every news item and every watchlist thesis needs a real source URL you actually opened.
  If you can't find a price, use `null` - never invent one.
- Prefer primary and reputable sources (company IR / press releases, SEC filings, CNBC,
  Bloomberg, Reuters, WSJ, FT, TechCrunch) over aggregator / content-farm sites.
- Owner-maintained files are read-only for you: `data/profile.json`, `data/holdings.json`,
  `data/loves.json`. Only edit them if the owner explicitly asks in the prompt.
- You update the site **only** through `merge.py` (one JSON run file). Don't hand-edit
  `data/status.json`, `data/watchlist.json`, `data/news.json` or `index.html`.
- Themes: AI, Internet, Machinery (robotics / automation / industrial), Energy (solar,
  storage, grid, nuclear, resilience). Growth first, but a moat matters.
- Watchlist is capped at 15. Quality over quantity: add at most 3 new names per run,
  and remove names whose thesis has broken (`"remove": true` with a reason).
- Be concise. Site copy is plain text, Craigslist-style. No hype, no emoji.

## Procedure

1. **Orient**
   ```bash
   cd "$(git rev-parse --show-toplevel)" && git pull --rebase --autostash origin main
   date -u +%Y-%m-%dT%H:%M
   cat data/holdings.json data/loves.json
   cat data/status.json data/watchlist.json
   python3 -c "import json;[print(n['date'],n['ticker'],n['source']) for n in json.load(open('data/news.json'))[:40]]"
   ```
   Note what's already covered so you don't re-add the same news URLs.

2. **Research** (use the Agent tool to fan out in parallel - one agent per group works well;
   give each the output-file path and the exact JSON shape):
   - **Holdings**: for every ticker in `data/holdings.json`, the material news since the
     last run (earnings, guidance, deals, regulation, big price moves), an approximate
     latest price in USD, and a take: `hold | add | trim | watch` with a one-sentence reason.
   - **Loved companies**: material news for the names in `data/loves.json` (public and
     private; for private note valuation / funding / ARR when reported).
   - **Watchlist**: re-check each existing entry (thesis intact? status/conviction change?
     new catalyst?), then hunt for new high-growth candidates across the four themes.
     Prefer real revenue growth + durable moat; label speculative names low conviction.
     Never add a ticker that is already a holding.
   - **AI bubble bellwethers**: refresh every indicator in `data/indicators.json` (same
     `key`s) with the latest observable reading, trend and signal - GPU rental $/hour,
     $/GW build cost, hyperscaler capex vs revenue, neocloud financing, HBM pricing, etc.
     Only change the explainer if the picture has actually changed. A new indicator is fine
     if it is observable from public data and clearly better than one already there.
   - **Calendar**: keep `data/calendar.json` covering today + 14 days: US macro releases
     (PCE, CPI, jobs, GDP, ISM), Fed / RBA decisions, minutes and major speeches, earnings
     and investor events for every holding, watchlist pick and loved company, product events
     (Apple, Google, Meta, Nvidia keynotes), and AI-compute bellwether dates. Verify every
     date on the source page; `time` is "TBC" if unconfirmed. Use stable keys like
     `2026-08-26-nvda-earnings` so re-runs update rather than duplicate; `"remove": true`
     for events that were cancelled or moved.
   - **Macro**: 3-5 sentences on the backdrop that matters for these themes right now
     (rates, AI capex, semis, energy policy, China).

3. **Write one run file** at `/tmp/market-research-run.json` (or the scratchpad dir):
   ```json
   {
     "as_of": "YYYY-MM-DDTHH:MM",
     "market_summary": "...",
     "headlines": ["3-6 one-liners: what changed since last run, most important first"],
     "takes": {"NVDA": {"take": "hold", "reason": "...", "price_usd": 0.0}},
     "watchlist": [
       {"ticker": "X", "exchange": "US", "name": "...", "sector": "AI",
        "status": "buy", "conviction": "high", "thesis": "...", "risks": "...",
        "price_usd": 0.0, "catalyst": "...", "source": "https://..."},
       {"ticker": "Y", "exchange": "US", "remove": true, "reason": "..."}
     ],
     "news": [
       {"date": "YYYY-MM-DD", "ticker": "NVDA", "headline": "...", "summary": "...",
        "source": "https://...", "impact": "positive"}
     ],
     "indicators": {"explainer": "optional", "items": [
       {"key": "h100_hour", "name": "...", "value": "$2.10", "trend": "down", "signal": "bearish",
        "why": "...", "watch": "...", "note": "...", "source": "https://..."}]},
     "calendar": [
       {"key": "2026-08-26-nvda-earnings", "date": "2026-08-26", "time": "after US close", "ticker": "NVDA",
        "title": "...", "type": "earnings", "why": "...", "link": "https://..."}],
     "notes": "anything worth recording for the log: what you looked at, what you skipped, open questions"
   }
   ```
   Enumerations - sector: `AI|Internet|Machinery|Energy`; status: `buy|accumulate|watch|avoid`;
   conviction: `high|medium|low`; take: `hold|add|trim|watch`; impact: `positive|negative|neutral`;
   event type: `earnings|macro|central_bank|product|conference|other`;
   trend: `up|flat|down`; signal: `bullish|neutral|bearish` (from the AI-infra investor's view:
   bullish = supply-constrained, bearish = compute being discounted).
   Use holding tickers exactly as in `holdings.json` (private: `STRIPE`, `OPENAI`);
   for loved private companies use `ANTHROPIC`, `CURSOR`. Include takes for **all** holdings
   every run (price refresh), even if the take is unchanged.
   For private holdings (`cost_usd` / `cost_date` in `holdings.json`) add `"mark_multiple"`:
   latest reported valuation divided by the valuation at `cost_date` (e.g. `2.27`), plus the
   source in the reason. Only change it when a new round / tender / secondary mark is reported.

4. **Merge, build, verify**
   ```bash
   python3 merge.py /tmp/market-research-run.json
   python3 build.py --check
   ```
   `merge.py` validates enumerations, dedupes news by URL, caps the watchlist, writes
   `research/<stamp>.md` and rebuilds `index.html`. If it exits non-zero, fix the run file
   and re-run it - do not hand-patch the data files.

5. **Publish**
   ```bash
   git add -A
   git commit -m "research: $(date -u +'%Y-%m-%d %H:%M') UTC"
   git push origin main
   ```
   If push is rejected, `git pull --rebase origin main` and push again.

6. **Report** in 5-10 lines: date, notable holding news, watchlist changes, and the
   commit hash. No need to repeat the whole log.

## If the prompt carries extra instructions

Treat text after `/market-research` as owner instructions for this run (e.g. "add 20 units
of NVDA", "drop SPOT from loves", "focus on nuclear"). Holding/loves changes are the one
case where you may edit the owner files; do it before step 2 and mention it in the report.
