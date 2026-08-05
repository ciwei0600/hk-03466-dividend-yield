# 03466.HK Dividend Yield Dashboard

Static dashboard for 03466.HK daily annualized TTM dividend yield and official HSHD30 constituent monitoring.

## Version

- Version: `0.5.0`
- Updated: `2026-08-05 11:25 CST`

## Data

- Close prices: Data_Server `/v1/hk-equity-quotes`
- Distributions: Data_Server `/v1/hk-etp-distributions`, sourced from Hang Seng Investment
- HSHD30 constituents: Hang Seng Indexes official public `constituents.do` endpoint

## Calculation

Daily dividend yield uses the annualized rule:

```text
annualized_dividend = sum(known monthly dividends) + latest_monthly_dividend * missing_months_to_12
yield = annualized_dividend / daily_close
```

Before the first ex-dividend date, there is no current monthly dividend and no yield is plotted.

## Daily Update

The page tries the daily yield and constituent snapshots under `runtime-data/` first and falls back to release snapshots under `assets/`.

On Quant, deployment installs two independent jobs:

```bash
5 18 * * 1-5 python3 scripts/update-data.py
10 7 * * * python3 scripts/update-data.py --constituents-only
```

The weekday job refreshes prices and distributions from Data_Server after market close. The daily constituent job directly checks the Hang Seng Indexes official endpoint once at `07:10 CST`; it validates the HSHD30 series, exactly 30 unique symbols, and records additions/removals against the previous successful snapshot.

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
