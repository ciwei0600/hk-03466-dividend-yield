# 红利 ETF 数据契约

## 03466 Price Data

- Source: Data_Server `/v1/hk-equity-quotes`
- Symbol: `03466`
- Currency: HKD
- Exactly one row is retained per trade date. Matching multi-source duplicates are collapsed; conflicting closes abort the update.
- Release snapshots are refreshed from the live API when a version is built.

## 03466 Distribution Data

- Source: Hang Seng Investment official `etffunddetail` structured API
- Trust: `H0E329`
- Class selection: `Fund_code=3466` and `Class_curr_symbol=HKD`
- Listing date: `2025-04-07`; any earlier distribution causes the update to fail
- Data_Server `/v1/hk-etp-distributions` is not used for this calculation, per the user's explicit source decision.

## 03466 Constituent Data

- Index: Hang Seng High Dividend 30 Index (`HSHD30`)
- Membership source: Hang Seng Indexes official public `constituents.do` endpoint
- Portfolio-weight source: Hang Seng Investment official 03466 portfolio composition `H0E329.xml`
- Company-profile source: HKEX official equity quote profile in Simplified Chinese; HKEX identifies LSEG Data & Analytics as the profile provider
- All three official sources are fetched directly once daily at `07:10 CST`; Data_Server is not used for constituents, weights, company names or business introductions
- Codes are normalized to a five-digit `symbol` and a complete `full_symbol` such as `00371.HK`
- Validation: `seriesCode=hshd30`, exactly 30 unique symbols in both membership and portfolio files, exact symbol-set equality, positive holding weights reconciling to the official stock allocation, and 30 non-empty HKEX company profiles
- A failed source, count mismatch, duplicate code, membership/portfolio mismatch, invalid weight or missing business introduction aborts the entire update and preserves the previous successful snapshot
- Successful snapshots are compared by stock code. Additions/removals are appended to `constituent_changes.json`; the latest event remains in `constituents_summary.json` so the page keeps showing it after later no-change syncs.
- Data_Server request `471ba741-c8c2-4165-b78a-0d5b35273725` was rejected after the user explicitly chose direct official sourcing; it is not a project dependency.

## 03466 Calculation

Use ex-dividend date. For each trade date:

```text
known = latest distributions with ex_date <= trade_date, capped at 12 monthly rows
annualized = sum(known) + latest_known_monthly_dividend * (12 - count(known))
yield = annualized / close
```

Before the first listed-class ex-dividend date, the yield must remain blank.

## 515080.SH

- Listing date: 2019-12-27, currency: CNY.
- Quotes: Data_Server `/v1/cn-equity-quotes`, explicit `market=SH&adjustment=raw`, bounded 90-day reads and recursive split at1,000 rows. Verify identity, dates, positive closes, and same-date source consistency.
- Pending request `522b0258-c618-4ba0-b6e2-4a411d0f5d35`, missing raw history uses Tencent's publicly available `day` (never `qfqday`) unadjusted bars. Annual windows, conservative source pacing, overlap consistency, first listing date and non-regressing history checks. Public summary labels temporary source. Once Data_Server supplies complete raw coverage, it is preferred automatically.
- Dividends: Data_Server `/v1/cn-etf-distributions`, `fund_code=515080`, `source_id=cmfchina`, currency CNY. Each amount is divided by10. Reject empty/truncated responses, wrong identity/unit/currency, pre-listing or duplicate ex-dates.
- Calculation: sum actual cash distributions where `trade_date-365 days < ex_date <= trade_date`, divided by that date's raw close. Future distributions excluded, no monthly extrapolation. Before first distribution yield is blank; an empty trailing window afterwards means0.
- Membership: CSI official `000922cons.xls`, exactly100 unique symbols, one date, index000922. Exchange names map SH/SZ/BJ explicitly. Track additions/removals across successful snapshots and retain latest change.
- Index weights: CSI `000922closeweight.xls`, exactly100 unique names and total100% (rounding tolerance0.1%). Show weight-as-of independently; when membership changes, a missing weight remains missing.
- Actual fund weights: `assets/515080_disclosed_holdings.json`, verified CMF2026 interim report, section7.3.1 index investment only. 100 holdings,99.39% of net assets (rounded disclosed weights); do not compare against98.97% of total assets, which has a different denominator. This is a dated disclosure, not a real-time portfolio; new official report import requires review and GitHub publication.
- Company names: latest CSI list; industries: Data_Server `/v1/cn-equity-securities`. Business descriptions remain unavailable, not inferred from industry.
- Separate output files prefixed515080; no overwrite of03466. Never reuse HKD names for CNY exports. Missing source, malformed data or conflicts preserve the previous successful snapshot.
