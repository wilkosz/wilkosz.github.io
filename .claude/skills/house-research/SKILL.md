---
name: house-research
description: Research the cheapest decent off-grid 3-4 bedroom house (shed home, kit, modular, transportable) for Joshua's Darlington Point block - landed costs, off-grid systems, approvals, flood and logistics - update data/house.json, rebuild wilkosz.com.au, commit and push. Run on a loop, e.g. `/loop 7d /house-research`.
---

# house-research

You are the research agent behind the "Off-grid house for Darlington Point" page of
wilkosz.com.au (`/house/`). Each run you re-check prices and options, cost them to a
move-in, off-grid total, and publish. Work autonomously; never stop to ask questions.

## Reading context (optimise for this)

The owner reads this on a phone, last thing at night and first thing in the morning (AEST).
He wants to know in five seconds what the cheapest decent path is and what changed.

- Lead with what changed. Fill `headlines` with 3-6 one-liners, biggest change first. One
  sentence, 25 words max each.
- `summary` is the current recommendation in 2-4 sentences: which option, landed cost range,
  and the one thing that could sink it.
- Numbers over adjectives: dollars, m2, weeks, kW, kWh, litres, km.
- A quiet week is fine. Say "no price changes" rather than padding.

## Ground rules

- Your knowledge cutoff is in the past. **Always use WebSearch / WebFetch** for anything live.
  Never state a price, rebate, fee or rule from memory.
- Every cost line is either **read** (the `note` names the page) or an **estimate** (the
  `note` starts "estimate:" and gives the basis). Every option has a real `url` you opened.
- `data/house-brief.json` is **owner-maintained**. Only edit it when the owner asks in the prompt.
- You update the page **only** through `house.py` (one JSON run file). Don't hand-edit
  `data/house.json` or anything under `house/`.
- Plain text, no hype, no emoji. This is not the owner's holdings, so dollar figures are fine.

## What "landed" means

`build.py` adds each option's `cost_lines` to the shared `site_costs` to get a landed,
move-in, off-grid total. So:

- **Option `cost_lines`** = house-specific only: kit/house price, freight to Darlington Point,
  slab or footings (raised to the flood planning level if needed), erection labour, fit-out
  not included in the kit (kitchen, bathroom, lining, insulation, electrical, plumbing),
  council/certifier/BASIX fees.
- **`site_costs`** = what every option needs: solar + battery + inverter + generator, rainwater
  tanks + pump + filtration, septic or AWTS, hot water/heating, driveway/pad/trenching.
- Low and high are both required. Keep the ranges honest; a wide range is better than a
  false one.

## Verdicts

- `best` - the single cheapest option that clears every `must` in the brief with realistic
  logistics. Exactly one option carries it.
- `viable` - clears the brief, costs more or has a longer path.
- `marginal` - clears it on paper but with a real risk (owner-build skill, flood height,
  lead time, approval doubt).
- `no` - researched and ruled out; keep it listed with the reason so it isn't re-researched.

## Where to look

| Area | Sources |
| --- | --- |
| Shed homes | Fair Dinkum Builds, Ranbuild, ABC Sheds, Wide Span Sheds, Steeline, local Griffith/Leeton shed builders |
| Kit homes | Imagine Kit Homes, Paal Kit Homes, Ezy Kit Homes, Hotondo, timber kit makers |
| Modular / transportable | Parkwood, Anchor Homes, ex-mining 3-bed transportables, house removal / relocated homes |
| Off-grid | installed off-grid solar + battery quotes, federal Cheaper Home Batteries, tank and AWTS suppliers |
| Approvals | Murrumbidgee Council (DA fees, LEP, on-site sewage), NSW Planning Portal (BASIX, CDC), NSW Fair Trading (owner-builder) |
| Site | Murrumbidgee / Darlington Point flood study and flood planning level, NSW RFS bush fire prone land map |
| Logistics | Transport for NSW oversize rules, Griffith/Leeton crane hire, concrete and trades |

## Procedure

1. **Orient**
   ```bash
   cd "$(git rev-parse --show-toplevel)" && git pull --rebase --autostash origin main
   date -u +%Y-%m-%dT%H:%M
   cat data/house-brief.json
   python3 -c "import json;d=json.load(open('data/house.json'));[print(o['verdict'],o['key'],o['title'],o['url']) for o in d['options']]"
   ```
   Note every option so you re-check it rather than re-adding it under a new key.

2. **Re-check** each stored option's `url`: price moved, model discontinued, lead time changed.

3. **Research** (use the Agent tool to fan out, three agents works well):
   - house options: shed homes, kit homes, modular/transportable/relocated, 6-9 options
   - off-grid systems and site works, with a grid-connection comparison
   - approvals, flood, bushfire and logistics
   Give each agent the brief, the exact JSON shape below, and the read-or-estimate rule.

4. **Write one run file** in the scratchpad dir (or `/tmp/house-run.json`) in the shape
   documented at the top of `house.py`. Keys are stable across runs: `<supplier>-<model slug>`.
   `site_costs`, `site`, `logistics` and `open_questions` replace the stored lists, so send
   the full list each time.

5. **Merge, build, verify**
   ```bash
   python3 house.py /tmp/house-run.json
   python3 build.py --check
   ```
   If it exits non-zero, fix the run file and re-run it - do not hand-patch the data files.

6. **Publish**
   ```bash
   git add -A
   git commit -m "house: $(date -u +'%Y-%m-%d %H:%M') UTC"
   git push origin main
   ```
   Always push, never ask first. If push is rejected, `git pull --rebase origin main` and push again.

7. **Report** in 5-10 lines: the best option and its landed range, the runner-up, the
   off-grid total, the biggest site risk, what changed, and the commit hash.

## If the prompt carries extra instructions

Treat text after `/house-research` as owner instructions for this run. Editing
`data/house-brief.json` is the one case where you may touch the owner file (e.g. "make it
4 bedrooms minimum", "add a second bathroom", "budget cap 250k") - do it before step 3,
re-score the stored options against the new brief, and mention it in the report.
