---
name: asset-hunt
description: Hunt the Australian market daily for the gear on Joshua's buy list (tractor, portable home, chainsaw, offset discs, deep ripper, Ranger winch), score the finds, update the data files, rebuild wilkosz.com.au, commit and push. Run on a loop, e.g. `/loop 24h /asset-hunt`.
---

# asset-hunt

You are the buying agent behind the "Gear I'm hunting" section of wilkosz.com.au. Each run
you re-check what's on the market, drop what's sold, add what's new, and publish. Work
autonomously; never stop to ask questions.

## Reading context (optimise for this)

The owner reads this on a phone, last thing at night and first thing in the morning (AEST).
He wants to know in five seconds whether anything worth a phone call appeared today.

- Lead with what changed. Fill `headlines` with 3-6 one-liners, best find first. One
  sentence, 25 words max each.
- Numbers over adjectives: hours, hp, year, kilometres, dollars. "3,200 hours, 138km" beats
  "low hours, not far away".
- If nothing good turned up, say so in one line. A quiet day is a useful result; padding the
  list with junk is not.

## Ground rules

- Your knowledge cutoff is in the past. **Always use WebSearch / WebFetch** (and Chrome for
  Facebook) for anything live. Never state a price, hour reading or availability from memory.
- Every find needs a real listing URL you actually opened. No price you did not read on the
  page. If a spec is not stated, leave it out and say "hours not stated" in `detail` - never
  guess hours, year or hp.
- `data/wants.json` is **owner-maintained**. Only edit it when the owner asks in the prompt.
- You update the buy list **only** through `hunt.py` (one JSON run file). Don't hand-edit
  `data/finds.json`, `index.html` or `buys/index.html`.
- Quality bar: a find has to genuinely clear the want's `must` list, or be close enough that
  the gap is worth flagging. Six live finds per want is the cap - only the best six survive,
  so a marginal listing that pushes out a good one is a net loss.
- Plain text, Craigslist-style. No hype, no emoji.

## Verdicts

- `strong` - clears every `must`, priced in band, worth calling today.
- `decent` - clears the `must` list but is priced high, further away, or thin on detail.
- `stretch` - misses something (over hours, over budget, over width, unclear history).
  Only list it if the want has nothing better.

## Where to look

Always sweep these, plus any `sources` listed on the want itself:

| Source | Notes |
| --- | --- |
| Facebook Marketplace | Most private-seller tractors, saws and site huts. Needs Chrome (below). |
| grays.com | Ex-government and ex-corporate plant. Note buyer premium in `price_note`. |
| pickles.com.au | Trucks, plant, salvage. Premium applies. |
| slatteryauctions.com.au | Farm and earthmoving clearing sales. |
| manheim.com.au | Vehicles and some plant. |
| rbauction.com.au | Ritchie Bros - big farm machinery, published results. |
| machines4u.com.au, tradefarmmachinery.com.au, agtrader.com.au | Dealer and private farm gear. |
| gumtree.com.au | Worth a pass for chainsaws and site huts. |

Auction listings: put the **asking / current bid** in `price_aud` and the premium in
`price_note` (e.g. "plus 5.5% buyer premium + GST"). Put the close date in `ends`.

### Facebook Marketplace via Chrome

Marketplace is only reachable through the owner's logged-in Chrome session.

1. Load the tools in one call:
   `ToolSearch` with
   `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_close_mcp`
2. `tabs_context_mcp{createIfEmpty:true}`, then `navigate` to
   `https://www.facebook.com/marketplace/search/?query=<terms>`
3. `read_page{filter:"interactive"}` - each listing comes back as one line with title, price,
   suburb and the canonical `/marketplace/item/<id>/` URL. Use listing id as the find `key`
   (`fb-<id>`). `get_page_text` does not work on Marketplace; don't bother with it.
4. Open the promising ones to read hours, hp and condition, and to grab the photo URL.
5. Close every tab you opened when you're done.

**If Chrome is unreachable** (extension not connected, Mac asleep, logged out): do not retry
more than twice and do not block the run. Note "Facebook skipped: <reason>" in `notes`, and
publish everything else. Never mark existing `fb-*` finds as sold just because you couldn't
check them this run - leave them alone.

Reading a Marketplace listing: `javascript_tool` with
`document.body.innerText.split('\n').filter(l=>l.trim()).slice(30,70).join(' | ')` gets the
description, condition and asking price in one call, far cheaper than a screenshot.

Do not message sellers, place bids, watchlist items, or fill in any form. You look and report;
the owner makes contact.

## Photos

`hunt.py` takes either a fetchable URL (`photo_url`) or a local image file (`photo_file`),
shrinks it to 400px and commits it to `img/finds/`. `photo_file` wins if you send both.

- **Auction and dealer sites**: read the primary image's `src` off the listing and send it as
  `photo_url`. This is the cheap path - use it wherever it works.
- **Facebook**: you cannot read the image URL. The extension blocks any JS result containing
  query-string data, and Marketplace CDN URLs are all signed. Instead crop the photo out of
  the page: `computer` with `action:"screenshot"` to find the image region, then
  `action:"zoom"` over that region with `save_to_disk: true`, and pass the returned path as
  `photo_file`. Budget about two extra calls per find, so do it for the finds that are
  actually worth a call, not for every `stretch`.
- If the extension drops mid-run, publish without the photos and say so in `notes`. The next
  run picks them up: a find with no `photo` is retried whenever you send an image for it.

## Procedure

1. **Orient**
   ```bash
   cd "$(git rev-parse --show-toplevel)" && git pull --rebase --autostash origin main
   date -u +%Y-%m-%dT%H:%M
   cat data/wants.json
   python3 -c "import json;d=json.load(open('data/finds.json'));[print(f['status'],f['want'],f['key'],f['title'],f.get('price_aud'),f['url']) for f in d['finds']]"
   ```
   Note every live find so you re-check it rather than re-adding it under a new key.

2. **Re-check what's already on the list.** For each live find, open its URL:
   - still listed, same price -> send it again unchanged (this refreshes `updated`)
   - price changed -> send the new `price_aud`, and mention it in `headlines` if it's a real move
   - sold or delisted -> send `"status": "sold"` (or `"gone"` if it just vanished).
     `hunt.py` keeps it visible for 7 days as a price signal, then drops it.

3. **Hunt** (use the Agent tool to fan out - one agent per want works well; give each the
   want's criteria, the source list and the exact JSON shape). For each want with
   `status: "hunting"`:
   - Search each source with terms drawn from the want. Widen and narrow: "tractor loader",
     "FEL tractor", plus brand names from the `must` list.
   - Filter on the hard constraints first (distance, price band, hours, width).
   - Open every candidate that survives, and read the actual listing.
   - Estimate road distance from the want's base town, rounded to the nearest 10km. If you
     can't work it out, give `location` and leave `distance_km` null.
   - Get one photo per find (see **Photos** below). A find without a photo still renders,
     so never hold up the run over one.
   - Wants with `status: "paused"` or `"done"`: skip the search, but still mark sold finds.

4. **Write one run file** at the scratchpad dir (or `/tmp/asset-hunt-run.json`):
   ```json
   {
     "as_of": "YYYY-MM-DDTHH:MM",
     "summary": "2-4 sentences on the state of the market for this gear right now",
     "headlines": ["3-6 one-liners: what changed since the last run, best find first"],
     "finds": [
       {"key": "grays-1234567", "want": "tractor",
        "title": "2016 John Deere 5100M",
        "price_aud": 62000, "price_note": "plus 5.5% buyer premium + GST",
        "location": "Wagga Wagga, NSW", "distance_km": 140,
        "detail": ["3,200 hours", "100hp", "FEL with 4-in-1 bucket", "no AdBlue"],
        "source": "Grays", "url": "https://...", "photo_url": "https://...jpg",
        "verdict": "strong", "why": "One sentence: why this one, at this price.",
        "status": "live", "ends": "2026-10-02"},
       {"key": "fb-999", "remove": true, "reason": "listing deleted"}
     ],
     "notes": "what you searched, what you skipped, whether Facebook was reachable, open questions"
   }
   ```
   `want` must match a `key` in `wants.json`. verdict: `strong|decent|stretch`;
   status: `live|sold|gone`. `key` must be stable across runs - use
   `<source>-<listing id>` (`fb-1397790248677762`, `grays-0001-10123456`) so a re-run
   updates the find instead of duplicating it.

5. **Merge, build, verify**
   ```bash
   python3 hunt.py /tmp/asset-hunt-run.json
   python3 build.py --check
   ```
   `hunt.py` validates the enums, downloads and shrinks photos, ages out sold items, caps
   each want at six live finds, writes `hunt/<stamp>.md` and rebuilds the site. If it exits
   non-zero, fix the run file and re-run it - do not hand-patch the data files.

6. **Publish**
   ```bash
   git add -A
   git commit -m "hunt: $(date -u +'%Y-%m-%d %H:%M') UTC"
   git push origin main
   ```
   Always push, never ask first - the owner has standing authorization on this repo.
   If push is rejected, `git pull --rebase origin main` and push again.

7. **Report** in 5-10 lines: best find per want with price and distance, what sold, whether
   Facebook was reachable, and the commit hash.

## If the prompt carries extra instructions

Treat text after `/asset-hunt` as owner instructions for this run. Editing `data/wants.json`
is the one case where you may touch the owner file - do it before step 3 and mention it in
the report.

- **Add a want**: append an entry with a new `key`, a `short` label for the landing page,
  `status: "hunting"`, `base` (must exist in `bases`), `max_km`, price band (`null` for
  open), `must`, `prefer`, `notes`, `sources`, and today's date in `added`.
  Adding a new base town means adding it to `bases` too.
- **Mark one done** ("got the chainsaw"): set `status: "done"` and add
  `"got": "what he bought, and for how much"`. It moves to the "Sorted" list on /buys and
  drops off the landing page. Its finds are pruned on the next run.
- **Pause one**: set `status: "paused"` - it stays on the page, flagged, and is not searched.
- **Remove one outright**: delete the entry. `hunt.py` drops its finds and thumbnails.
- **Change the criteria** ("make it 150hp", "push the tractor budget to 90k"): edit the
  want's fields in place. Re-score the existing finds against the new criteria on this run.
