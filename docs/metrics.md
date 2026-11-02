# Metrics registry (Section 6.5)

Single definition of every dashboard/report number. `app/services/dashboard.py`
is this document turned into code — the dashboard endpoints and every
report in the catalogue (`app/routers/reports.py`) call the *same*
functions, so there is no second, divergent implementation that could
silently drift from what's written here. `tests/test_dashboard_and_reports.py`
proves the R7/R11 gates: a tile's number equals an independent SQL
recomputation, and a report's total equals the dashboard's.

No `dashboard_counters` cache table exists yet (Section 6.5 describes one,
incrementally updated in the same transaction as every state change). At
this project's data volume, live recomputation on every request is both
simpler and cannot drift from reality by construction — see
`docs/limitations.md` for when that stops being true and the cache table
becomes worth building.

| Metric | SQL / computation | Owner | Refresh |
|---|---|---|---|
| **Total cases** | `SELECT count(*) FROM cases` | `compute_tiles` | live, every request |
| **Pending** | `count(*) WHERE status = 'pending'` | `compute_tiles` | live |
| **Under process** | `count(*) WHERE status = 'under_process'` | `compute_tiles` | live |
| **Escalated** | `count(*) WHERE status = 'escalated'` (shown as its own tile, not folded into "under process" — Section 6.5) | `compute_tiles` | live |
| **Transferred** | `count(*) WHERE status = 'transferred'` (cases currently in the transferred state; a separate "awaiting acceptance" tile counts in-flight transfer proposals — see below) | `compute_tiles` | live |
| **Disposed** | `count(*) WHERE status = 'disposed'` | `compute_tiles` | live |
| **Beyond timeline** | For every open (`status != 'disposed'`) case: `sla_status == "breached"` via `app/services/sla.py`'s business-day engine against the case's resolved SLA policy | `compute_tiles` | live |
| **Approaching** | Same per-case SLA resolution, `sla_status == "approaching"` (inside the policy's `warn_at` window) | `compute_tiles` | live |
| **Ageing buckets** | For every open case: `(today - received_at.date()).days`, bucketed at edges `0-5 / 6-10 / 11-20 / 21+` (calendar days, not business days — see docs/limitations.md for why these differ from the SLA engine's business-day maths) | `compute_tiles` | live |
| **Bureau/Cell workload** | Per `assigned_bureau_id`, among open cases: `open` = count, `overdue` = count where `sla_status == "breached"` | `compute_tiles` | live |
| **Transfers awaiting acceptance** | `count(*) FROM case_transfers WHERE state = 'proposed'` | `compute_tiles` | live |
| **Overlap queue** | `count(*) FROM overlap_candidates WHERE status = 'pending'`, plus the top 3 institutions by pending-candidate count | `compute_tiles` | live |
| **Monthly received vs disposed** | Bucket `cases.received_at` and `cases.disposed_at` by calendar month in application code (not a DB `date_trunc`, for independent testability — see `compute_monthly_series`'s docstring) | `compute_monthly_series` | live, last 6 months |
| **Disposal rate** (report only) | Per month: `disposed_count / received_count` where `received_count > 0`, else "n/a" | `reports.py::_disposal_rate` | live |

## Known simplifications (documented, not fabricated)

- **"Transferred (count in period)"** (Section 6.5's exact wording: "cases
  whose latest transfer event is in the period") is simplified to "cases
  currently in the `transferred` status" — computing the *latest* transfer
  event per case within an arbitrary period needs a window function this
  phase didn't build. The number shown is honest, just a different (and
  simpler) definition than the one in the master prompt; flagged here
  rather than silently matching the spec's wording without matching its
  behavior.
- **Disposal rate**'s true definition is `disposed_in_period / (open_at_start_of_period + received_in_period)`.
  There is no "open at start of period" snapshot, so the report uses
  `disposed_in_period / received_in_period` instead — a different, simpler
  ratio, not the spec's. Same reasoning as above.
- **Ageing buckets** use calendar days, not the SLA engine's business-day
  maths, because Section 6.5 doesn't specify which and calendar days are
  simpler to reason about for an ageing list (vs. a due-date computation).
