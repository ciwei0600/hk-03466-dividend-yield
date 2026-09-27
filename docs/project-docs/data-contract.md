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
- Calculation method: `trading_day_allocated_ttm_v1`, per the user's 2026-09-27 decision. Each completed payment is divided equally among actual quoted trading sessions in `(previous ex-date, current ex-date]`; the first interval includes the listing date. No calendar-day allocations or fixed 250/252-session assumptions. Reject missing ex-date quotes, duplicate ex-dates or truncated listing history. Every completed interval must conserve its official per-unit payment.
- TTM is the sum of daily allocations in `(trade_date minus 12 calendar months, trade_date]`, divided by raw close. February29 uses February28 in the preceding year. Before one full year of listing history, TTM is null; valid prices still appear. This replaces the historical annual/semiannual/quarterly frequency rule.
- Completed intervals intentionally rewrite historical allocations. This is retrospective dividend attribution, not point-in-time cash income, guaranteed returns, or a valid unqualified backtest input. Payments whose ex-date is later than the price snapshot remain excluded, even if already announced.
- The unfinished interval carries the latest completed interval's per-trading-day amount as an estimate. TTM windows containing estimated sessions use a dashed yield line; actual-price lines remain solid. After the next ex-date, overwrite that interval with equal allocations from the actual payment and redraw confirmed points as solid. A change in raw close can still change yield on the ex-date.
- Fields: `daily_dividend_cny`; `allocation_status` (`historical`/`estimated`); inclusive `allocation_period_start`/`allocation_period_end` (null end for unfinished interval); `allocation_trading_days` (null until complete); `allocation_source_ex_date` (the payment establishing the daily amount); `ttm_window_start_exclusive`, `ttm_trading_days`, `ttm_history_complete`, `ttm_estimated_trading_days`, `ttm_estimated_dividend_cny`. `ttm_dividend_cny` and `ttm_dividend_yield_pct` now carry this new method, guarded by the summary method version.
- Audit fields `actual_365d_dividend_count`, `actual_365d_dividend_cny`, `actual_365d_dividend_yield_pct` preserve the original strict cash-window calculation `(trade_date-365 days, trade_date]`. They may include3 or5 quarters around shifted ex-date anniversaries and do not drive the displayed curve.
- Summary carries `calculation_method`; frontend rejects outdated formula snapshots and falls back to the matching release snapshot. `--recalculate` reuses a matching published price snapshot, refreshes Data_Server official distributions and writes new calculations, preserving `price_snapshot_updated_at`. Routine updates still fetch current prices.
- Membership: CSI official `000922cons.xls`, exactly100 unique symbols, one date, index000922. Exchange names map SH/SZ/BJ explicitly. Track additions/removals across successful snapshots and retain latest change.
- Index weights: CSI `000922closeweight.xls`, exactly100 unique names and total100% (rounding tolerance0.1%). Show weight-as-of independently; when membership changes, a missing weight remains missing.
- Actual fund weights: `assets/515080_disclosed_holdings.json`, verified CMF2026 interim report, section7.3.1 index investment only. 100 holdings,99.39% of net assets (rounded disclosed weights); do not compare against98.97% of total assets, which has a different denominator. This is a dated disclosure, not a real-time portfolio; new official report import requires review and GitHub publication.
- Company names: latest CSI list; industries: Data_Server `/v1/cn-equity-securities`. Business descriptions remain unavailable, not inferred from industry.

## 515080 forward-adjusted price display (2026-09-27)

- Default chart price is `qfq_close`, with a raw toggle. Yield always uses `close`. Toggle preserves date, range and TTM; tooltip labels the display basis and raw yield denominator.
- `price_display_method=cash_dividend_forward_v1`: `qfq_close = close - sum(actual cash dividends where trade_date < ex_date <= qfq_anchor_date)`. No allocated or estimated dividends enter price adjustment. Ex-date itself excludes its own payment; latest raw/qfq match. This is a cash-distribution method for verified 515080 history, not a general split/consolidation algorithm.
- `qfq_cash_adjustment_cny` records the subtraction; summary carries `qfq_anchor_date`, provenance, method and upstream request. Future ex-dates are excluded and new completed distributions reanchor history. CSV raw `close` stays intact. Frontend rejects snapshots without a matching display method, anchor or consistent positive forward prices.
- Data_Server qfq returned 2019-12-31=0.640 (updated2026-08-06), while current THS forward/Tencent qfq=0.625. Difference0.015 matches the2026-09-16 dividend. Quality request `0189023c-9f00-400a-8d97-4a765d640705` submitted as `cash-ranking`; not completed. Stale values are documented and excluded, not silently merged. Derived display results matched all1636 current Tencent qfq rows on2026-09-27.
- Separate output files prefixed515080; no overwrite of03466. Never reuse HKD names for CNY exports. Missing source, malformed data or conflicts preserve the previous successful snapshot.
