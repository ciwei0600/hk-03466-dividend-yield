# Data Contract

## Price Data

- Source: Data_Server `/v1/hk-equity-quotes`
- Symbol: `03466`
- Currency: HKD
- Exactly one row is retained per trade date. Matching multi-source duplicates are collapsed; conflicting closes abort the update.
- Release snapshots are refreshed from the live API when a version is built.

## Distribution Data

- Source: Hang Seng Investment official `etffunddetail` structured API
- Trust: `H0E329`
- Class selection: `Fund_code=3466` and `Class_curr_symbol=HKD`
- Listing date: `2025-04-07`; any earlier distribution causes the update to fail
- Data_Server `/v1/hk-etp-distributions` is not used for this calculation, per the user's explicit source decision.

## Constituent Data

- Index: Hang Seng High Dividend 30 Index (`HSHD30`)
- Source: Hang Seng Indexes official public `constituents.do` endpoint, fetched directly once daily at `07:10 CST`
- Validation: `seriesCode=hshd30`, declared count `30`, exactly 30 unique constituent symbols
- Successful snapshots are compared by stock code. Additions/removals are appended to `constituent_changes.json`; the latest event remains in `constituents_summary.json` so the page keeps showing it after later no-change syncs.
- Data_Server request `471ba741-c8c2-4165-b78a-0d5b35273725` was rejected after the user explicitly chose direct official sourcing; it is not a project dependency.

## Calculation

Use ex-dividend date. For each trade date:

```text
known = latest distributions with ex_date <= trade_date, capped at 12 monthly rows
annualized = sum(known) + latest_known_monthly_dividend * (12 - count(known))
yield = annualized / close
```

Before the first listed-class ex-dividend date, the yield must remain blank.
