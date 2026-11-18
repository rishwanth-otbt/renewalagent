# Sample uploads — test scenarios

Upload these through the **📁 Upload** button. Each file name says what it tests and the expected result.
All vendors are fictional. Results below were checked with an assessment date of **2026-11-18**.

| File | What it tests | Expected result |
|---|---|---|
| `01_expect_renew_clean_good_performance_within_budget` | Happy path: +4%, Good SLA, under budget, within 6% cap | **Renew**, risk Low |
| `02_expect_renegotiate_price_cap_breach_8pct_vs_6pct_cap` | +8% vs 6% MSA cap, otherwise healthy and within budget | **Renegotiate**, cap breach |
| `03_expect_renegotiate_over_budget_small_increase_no_price_cap` | Only issue is $5k over approved budget; no price cap in MSA | **Renegotiate** |
| `04_expect_switch_price_shock_40pct_easy_to_replace` | +40% price, Low replacement difficulty, 3-month migration | **Switch / Benchmark** |
| `05_expect_switch_poor_sla_22pct_increase_not_downgraded_hard_to_replace` | Uptime 99.2% vs 99.9%, 4 outages, +22%; hard to replace but poor performance keeps it a switch | **Switch / Benchmark**, not downgraded |
| `06_expect_renegotiate_needs_improvement_outages_roadmap_backlog_low_increase` | Needs Improvement rating, 3 outages, 3 undelivered roadmap items, only +3% | **Renegotiate** |
| `07_expect_notice_imminent_risk_cutoff_within_21_days` | Notice cutoff 2026-12-05 (≤21 days away) | `IMMINENT_RISK`, “serve notice” first step |
| `08_expect_notice_missed_auto_renewal_lock_in_no_termination_right` | Notice missed + auto-renewal + no termination for convenience | `AUTO_RENEWED_LOCK_IN`, Renegotiate |
| `09_expect_renew_notice_closed_no_auto_renewal_sign_before_lapse` | Notice passed, no auto-renewal, good terms | **Renew**, `NOTICE_WINDOW_CLOSED`, sign before lapse |
| `10_expect_renegotiate_shelfware_68pct_with_unsupported_seat_expansion` | 68% utilization while vendor proposes +200 seats | **Renegotiate**, `EXPANSION`, right-size |
| `11_expect_renew_seat_reduction_and_module_removed` | 1000 → 950 seats, Legacy module dropped, 91% utilization | **Renew**, `REDUCTION` |
| `12_expect_renegotiate_bundled_new_modules_and_36_month_lock_in` | Two new modules bundled in, +14% on a 36-month term | **Renegotiate**, bundled-module flag |
| `13_expect_renegotiate_expired_addenda_and_unclaimed_service_credits` | 2 expired addenda, $9.5k unclaimed credits, 1 outage | **Renegotiate**, expired-addendum + credit flags |
| `14_expect_rejected_422_missing_required_fields` | Required fields removed | Upload **rejected (422)** listing 4 missing fields |
| `15_expect_rejected_422_wrong_types_and_invalid_values` | `"yes"` for boolean, `"1000"` for int, uptime 120%, bad addendum status | Upload **rejected (422)** |
| `16_expect_rejected_422_term_end_before_term_start` | Term end earlier than term start | Upload **rejected (422)** |

Older files (`demo_*`, `securenet_edr_renewal.json`) are SecureNet/DataGuard demo variants; `demo_dataguard_price_shock_35pct`
covers the “switch downgraded to renegotiate because vendor is hard to replace” case.

**Date-sensitive:** the app uses today's date. Files 07, 08 and 09 depend on where today falls against the notice cutoff, so
07 only shows `IMMINENT_RISK` until 2026-12-05. To reproduce exact results later, open the case with
`/api/case/<id>?as_of=2026-11-18`.
