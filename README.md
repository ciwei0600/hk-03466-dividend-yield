# 03466.HK Dividend Yield Dashboard

Static dashboard for 03466.HK daily annualized TTM dividend yield and official HSHD30 constituent monitoring.

## Version

- Version: `0.6.0`
- Updated: `2026-08-05 15:10 CST`

## Data

- Close prices: Data_Server `/v1/hk-equity-quotes`, normalized to one verified close per trade date
- Distributions: Hang Seng Investment official `etffunddetail` API, strictly the listed HKD counter `Fund_code=3466`
- HSHD30 constituents: Hang Seng Indexes official public `constituents.do` endpoint
- 03466 constituent weights: Hang Seng Investment official `H0E329.xml` portfolio composition
- Company names, industries and short business introductions: HKEX official equity quote company profiles (profile provider shown by HKEX: LSEG Data & Analytics)

## Calculation

Daily dividend yield uses the annualized rule:

```text
annualized_dividend = sum(known monthly dividends) + latest_monthly_dividend * missing_months_to_12
yield = annualized_dividend / daily_close
```

Before the first ex-dividend date, there is no current monthly dividend and no yield is plotted.

## Daily Update

The page tries the daily yield and constituent snapshots under `runtime-data/` first and falls back to release snapshots under `assets/`.
HTML, JavaScript and CSS are served with revalidation, and the page pins JavaScript/CSS URLs to the release version so a deployment cannot leave returning browsers on stale UI logic. Runtime snapshots are served with `no-store`.

On Quant, deployment installs two independent jobs:

```bash
5 18 * * 1-5 python3 scripts/update-data.py
10 7 * * * python3 scripts/update-data.py --constituents-only
```

The weekday job refreshes close prices from Data_Server and listed-class distributions directly from Hang Seng Investment after market close. Distribution rows are rejected if they predate the `2025-04-07` listing date, use a non-HKD currency, or repeat an ex-dividend date. Price rows are reduced to one row per trade date; conflicting same-day closes fail the update instead of silently changing the chart. The daily constituent job directly checks three official web sources once at `07:10 CST`: Hang Seng Indexes membership, Hang Seng Investment's complete 03466 portfolio composition, and HKEX company profiles. It writes a new snapshot only when all three contain 30 unique, exactly matching stock codes and every holding has a positive weight and non-empty business introduction. The page shows five-digit `.HK` codes, portfolio weights, short business introductions, the latest sync time, and constituent additions/removals; the most recent recorded change remains visible after later no-change runs.

## Local Preview

```bash
python3 -m http.server 8088
```

Open `http://127.0.0.1:8088/`.

## Deploy

Deployment must be GitHub-first:

```bash
git push
ssh quant
cd /opt/hk-03466-dividend-yield
git pull --ff-only
bash deploy/deploy-on-host.sh
```

Use environment variables on Quant when needed:

```bash
DEPLOY_PORT=80 DEPLOY_SERVER_NAME=03466-dividend.cw-info.top bash deploy/deploy-on-host.sh
```

HTTPS is enabled automatically when a Let's Encrypt certificate exists under
`/etc/letsencrypt/live/03466-dividend.cw-info.top/`.
