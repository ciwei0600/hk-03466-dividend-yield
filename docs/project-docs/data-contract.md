# Data Contract

## Price Data

- Source: Data_Server `/v1/hk-equity-quotes`
- Symbol: `03466`
- Currency: HKD
- Latest verified row in this release: `2026-06-30`, close `18.26`

## Dividend Data

- Temporary source: Hang Seng Investment official `etffunddetail` API
- Class: listed HKD counter, fund code `3466`
- Formal Data_Server request: `fcd695df-c1e0-4aa4-8ac5-617538509c8b`

## Calculation

Use ex-dividend date. For each trade date:

```text
known = latest distributions with ex_date <= trade_date, capped at 12 monthly rows
annualized = sum(known) + latest_known_monthly_dividend * (12 - count(known))
yield = annualized / close
```
