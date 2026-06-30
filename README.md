# 03466.HK Dividend Yield Dashboard

Static dashboard for 03466.HK daily annualized TTM dividend yield.

## Version

- Version: `0.4.3`
- Updated: `2026-06-30 16:15 CST`

## Data

- Close prices: Data_Server `/v1/hk-equity-quotes`
- Dividend snapshot: Hang Seng Investment official `etffunddetail` API, listed HKD counter 3466
- Data_Server work order for formal HK ETP distributions: `fcd695df-c1e0-4aa4-8ac5-617538509c8b`

## Calculation

Daily dividend yield uses the annualized rule:

```text
annualized_dividend = sum(known monthly dividends) + latest_monthly_dividend * missing_months_to_12
yield = annualized_dividend / daily_close
```

Before the first ex-dividend date, there is no current monthly dividend and no yield is plotted.

## Daily Update

The page tries `runtime-data/03466_ttm_dividend_yield_daily_annualized.csv` first and falls back to the release snapshot under `assets/`.

On Quant, deployment installs a weekday `18:05 CST` cron job:

```bash
python3 scripts/update-data.py
```

The script refreshes `runtime-data/` from Data_Server close prices and Hang Seng Investment dividend data.

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
