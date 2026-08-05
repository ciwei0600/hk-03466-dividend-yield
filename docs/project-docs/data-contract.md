# Data Contract

## Price Data

- Source: Data_Server `/v1/hk-equity-quotes`
- Symbol: `03466`
- Currency: HKD
- Release snapshots are refreshed from the live API when a version is built.

## Distribution Data

- Source: Data_Server `/v1/hk-etp-distributions`
- Symbol: `03466`
- Upstream source: Hang Seng Investment official structured API
- Completed Data_Server request: `fcd695df-c1e0-4aa4-8ac5-617538509c8b`

## Constituent Data

- Index: Hang Seng High Dividend 30 Index (`HSHD30`)
- Source: Hang Seng Indexes official public `constituents.do` endpoint, fetched directly once daily at `07:10 CST`
- Validation: `seriesCode=hshd30`, declared count `30`, exactly 30 unique constituent symbols
- Data_Server request `471ba741-c8c2-4165-b78a-0d5b35273725` was rejected after the user explicitly chose direct official sourcing; it is not a project dependency.

## Calculation

Use ex-dividend date. For each trade date:

```text
known = latest distributions with ex_date <= trade_date, capped at 12 monthly rows
annualized = sum(known) + latest_known_monthly_dividend * (12 - count(known))
yield = annualized / close
```
