# 05 — Ledger Schemas

## Scope

Schema sketches for the two authoritative payout-attribution tables, the cross-references between them, and the design principles (append-only, auditable, model-versioned) that protect contributor and SAR-org trust.

These are working schemas — column names and types are likely to evolve during implementation, but the *shape* (which fields, which invariants) should hold.

## Design principles

1. **Append-only at the database level.** Status transitions create new rows or update timestamped columns, never rewrite history. A reject that is later overturned is preserved alongside the overturning row; the audit trail is the source of truth, not the current state.
2. **Owner-visible.** Every row in either ledger is visible in the portal to the user/org it concerns, with no fields hidden. If a contributor or SAR admin can't see something we used to decide their pay, they can't trust the platform.
3. **Model-versioned.** Scoring decisions reference the exact model version used so disputes can be replayed.
4. **Period-scoped.** All payouts are bucketed into `payout_periods` (monthly). Once a period closes and disburses, its rows are frozen.
5. **No cross-service direct DB access.** `DataLedger` lives in SnowDB; `RescueLedger` lives in AvServ. rmdig-ai reads both through service APIs to compute payouts and present dashboards.

## Payout periods (rmdig-ai)

The clock that drives both ledgers' payout cycles.

```sql
-- rmdig-ai Postgres
payout_periods (
  id            uuid pk,
  period_start  date not null,
  period_end    date not null,
  status        text check (status in ('open', 'closing', 'closed')) not null default 'open',
  closed_at     timestamptz,
  data_pool_cents     bigint,      -- finalized at close
  response_pool_cents bigint,      -- finalized at close
  standby_paid_cents  bigint,      -- finalized at close
  unique (period_start, period_end)
)
```

Default cadence: calendar month, closing on the 1st of the following month, disbursement 3-5 business days after close (allows for late-arriving scoring and last-day reviews).

## DataLedger (SnowDB)

Source of truth for what each contributor is owed for data.

```sql
-- SnowDB Postgres
data_ledger (
  id                          uuid pk,
  capture_id                  uuid not null,             -- references captures(id)
  device_id                   text not null,             -- AvServ.devices.id at capture time
  user_id                     uuid,                      -- nullable for unlinked or anonymized
  captured_at                 timestamptz not null,
  region_policy_id            uuid not null,             -- references region_policies(id)
  
  -- Scoring
  scored_at                   timestamptz,
  novelty_score               numeric(5,4),              -- 0.0000 to 1.0000
  model_version_scored_against text,                     -- e.g., "snowgan-2026-04-01-rev3"
  payout_eligible             boolean,                   -- false if region saturated or score too low
  
  -- Cross-payout
  cross_payout_multiplier     int default 1,             -- 1, 10, or higher per policy
  cross_payout_rescue_id      uuid,                      -- references rescue_ledger.id if multiplier > 1
  
  -- Resample cap
  segment_resample_index      int,                       -- 1..N within (device_id, segment) group
  within_resample_cap         boolean,                   -- index <= region_policies.max_resamples_per_segment
  
  -- Pricing
  base_payout_cents           int not null,              -- from region_policy at scoring time
  payout_cents                int,                       -- = base × multiplier if eligible & within cap else 0
  
  -- Review
  status                      text check (status in (
                                'pending_scoring',
                                'pending_review',
                                'earned',
                                'rejected',
                                'paid'
                              )) not null,
  reviewed_at                 timestamptz,
  reviewed_by_user_id         uuid,                      -- references rmdig-ai users(id), denormalized
  reject_reason               text,                      -- enum code per 02_data_contribution.md
  reject_note                 text,
  
  -- Settlement
  paid_in_period_id           uuid,                      -- references rmdig-ai payout_periods(id)
  stripe_transfer_ref         text,
  
  -- Lifecycle
  anonymized_at               timestamptz,               -- set when user requests linkage removal
  
  created_at                  timestamptz default now(),
  updated_at                  timestamptz default now()
)

-- Audit trail: status changes append rows here, never mutate the main row's history
data_ledger_status_log (
  id              bigserial pk,
  data_ledger_id  uuid not null references data_ledger(id),
  from_status     text,
  to_status       text not null,
  actor_user_id   uuid,                                  -- nullable for system transitions
  reason          text,
  at              timestamptz default now()
)

-- Useful indices
create index on data_ledger (user_id, status);
create index on data_ledger (paid_in_period_id);
create index on data_ledger (cross_payout_rescue_id) where cross_payout_rescue_id is not null;
```

**Why these columns:**

- `model_version_scored_against` — replay disputes against the exact scoring model.
- `region_policy_id` — preserves which policy version was in force when scored, even if the policy is later updated.
- `cross_payout_rescue_id` — every cross-payout is traceable back to the rescue event that triggered the bonus. If a rescue is later determined invalid, the cross-payouts associated with it can be audited and (per policy) potentially clawed back before disbursement.
- `segment_resample_index` + `within_resample_cap` — resample cap is enforced at scoring, but the index is preserved so contributors can see why image 11 of a segment earned $0 (still accepted into dataset).
- `anonymized_at` — fulfills GDPR/CCPA requests without losing the row.

## RescueLedger (AvServ)

Source of truth for what each SAR org is owed for response work.

```sql
-- AvServ Postgres
rescue_ledger (
  id                       uuid pk,
  alert_id                 uuid not null,                -- AvServ alert/dispatch event id
  dispatch_dedup_key       text not null,                -- same primitive AvServ uses for cross-node dedup
  sar_org_id               uuid not null,                -- references rmdig-ai sar_orgs(id), denormalized
  
  -- Dispatch context (immutable from time of fire)
  dispatched_at            timestamptz not null,
  user_last_known_gps      geography(point),
  user_last_known_at       timestamptz,
  
  -- Engagement signals (filled as they occur)
  acked_at                 timestamptz,
  acked_by_user_id         uuid,
  
  movement_detected_at     timestamptz,                  -- first ping showing sustained convergence
  movement_distance_closed_m int,                        -- meters of convergent travel attributed
  movement_consent_responders uuid[],                    -- list of responders whose GPS contributed
  
  resolved_at              timestamptz,
  resolved_outcome         text,                         -- per follow-up report enum
  
  report_filed_at          timestamptz,
  report_id                uuid,                         -- references follow_up_reports(id)
  
  -- Computed tier (derived from signals at period close)
  engagement_tier          text check (engagement_tier in (
                              'ack_only',
                              'ack_movement',
                              'full'
                            )),
  tier_weight              numeric(3,2),                 -- 0.10, 1.00, 1.50 per current policy
  
  -- Settlement (filled when period closes)
  paid_in_period_id        uuid,                         -- references rmdig-ai payout_periods(id)
  pool_share_cents         int,
  
  created_at               timestamptz default now(),
  updated_at               timestamptz default now(),
  
  unique (dispatch_dedup_key, sar_org_id)               -- one row per (logical-dispatch × org)
)

-- One follow-up report per resolved rescue (filed by one responder, links the rescue to its outcome record)
follow_up_reports (
  id                       uuid pk,
  rescue_ledger_ids        uuid[] not null,             -- one report can close multiple orgs' entries
  filed_by_user_id         uuid not null,
  filed_at                 timestamptz default now(),
  
  -- CAIC-aligned fields (see 03_sar_workflow.md for full list)
  incident_at              timestamptz not null,
  incident_location        geography(point),
  activity                 text,
  party_size               int,
  party_experience         text,
  
  avalanche_involved       boolean,
  avalanche_size           text,
  avalanche_type           text,
  avalanche_trigger        text,
  slope_angle              int,
  aspect                   text,
  elevation                int,
  
  snowpack_observations    text,
  weather_observations     text,
  
  outcome                  text not null,
  search_duration_minutes  int,
  personnel_deployed       int,
  agencies_involved        text[],
  found_location           geography(point),
  
  notes                    text,
  
  -- RMDig extensions
  cross_payout_opportunity boolean default false,
  data_publish_consent     text check (data_publish_consent in ('none', 'anonymized', 'full')) default 'none'
)

create index on rescue_ledger (sar_org_id, paid_in_period_id);
create index on rescue_ledger (dispatched_at);
```

**Why these columns:**

- `dispatch_dedup_key` + `unique (dispatch_dedup_key, sar_org_id)` — reuses AvServ's existing cross-node dedup primitive to ensure one logical dispatch produces exactly one row per attributed org, even when both AvServ nodes' watchdogs fire.
- `movement_consent_responders` — only responders who opted in to GPS tracking contribute to the movement signal. Auditable list.
- `engagement_tier` + `tier_weight` — derived at period close from the engagement signals. Stored explicitly so a contributor can see exactly how their pay was computed (not recomputed on the fly each time the dashboard loads).
- `follow_up_reports.rescue_ledger_ids` (array) — multi-team rescues can be closed by a single report referencing all involved orgs' rescue_ledger entries. The report bonus credit applies to the filing responder's org; others can co-file or accept the existing report.

## Cross-references

```
DataLedger.cross_payout_rescue_id  ──►  RescueLedger.id
                                         (cross-payout bonus is tied to the rescue that triggered it)

RescueLedger.report_id              ──►  follow_up_reports.id
                                         (full-tier credit requires a report)

DataLedger.paid_in_period_id        ──►  payout_periods.id (rmdig-ai)
RescueLedger.paid_in_period_id      ──►  payout_periods.id (rmdig-ai)
                                         (same period clock for both ledgers)
```

**Sequencing constraint:** a period cannot close until:
1. All `DataLedger` rows with `captured_at` in the period have status ≠ `pending_scoring` and ≠ `pending_review`. (Implies scoring and review must catch up.)
2. All `RescueLedger` rows with `dispatched_at` in the period have either a resolution or have exceeded the report-window deadline (e.g., 14 days after dispatch).

The portal's payout dashboard surfaces "period closing in N days, X pending items" to operators so backlog is visible.

## Period-close job (rmdig-ai)

Pseudocode for the monthly settlement:

```
on period_end + 5 business days:
  ensure all data_ledger and rescue_ledger entries for the period are settled (status final)
  
  data_pool_cents = sum(payout_cents) for data_ledger where status='earned' and period matches
  
  total_weight = sum(tier_weight) for rescue_ledger where period matches
  response_pool_cents = max(0, period_profit_pool - data_pool_cents)
  
  for each rescue_ledger row in period:
    pool_share_cents = (tier_weight / total_weight) × response_pool_cents
    set paid_in_period_id, pool_share_cents
  
  for each sar_org with rows in period:
    org_total = sum(pool_share_cents) for that org
    + monthly_standby_retainer
    issue Stripe Connect transfer to org's connected account
  
  for each user with earned data_ledger rows in period:
    user_total = sum(payout_cents) for that user
    if user.w9_or_stripe_express_complete:
      issue Stripe Connect transfer
    else:
      hold in pending_disbursement bucket, notify user
  
  mark payout_periods row status='closed', set finalized totals
```

## Auditability surface (portal)

Each user/org sees their ledger as a paginated table:

- Contributors: every `data_ledger` row, filterable by status, sortable by date, with drilldown showing the capture, the scoring details, and (if rejected) the reason.
- SAR admins: every `rescue_ledger` row attributed to their org, filterable by status, with drilldown showing the alert, engagement signals, tier weight, and (if paid) pool share calculation.
- RMDig operators: cross-org views, period summaries, the finalized pool totals, anomaly detection (e.g., a contributor whose acceptance rate suddenly drops to 0).

## Open questions

- **Late-arriving evidence:** if a SAR team files a report 30 days after dispatch (past the report window), do they earn the report-tier bonus retroactively? Recommend: yes, but only out of a subsequent period's pool, not the original. Keeps the original period's settlement clean.
- **Clawback policy:** if a `cross_payout_rescue_id` is later determined to be a false dispatch (no real incident), do related data cross-payouts get clawed back? Recommend: only if not yet disbursed; once paid, treat as a sunk cost of doing business.
- **Pool reserves:** should some fraction of the profit pool be held back as a dispute reserve? Recommend yes, ~5% of monthly pool, with quarterly true-up of unused reserve to the next period.

## Related docs

- [00_platform_architecture.md](00_platform_architecture.md) — service boundaries, database isolation
- [02_data_contribution.md](02_data_contribution.md) — DataLedger contextual flow
- [03_sar_workflow.md](03_sar_workflow.md) — RescueLedger contextual flow, engagement tiers
- [04_payments_and_legal.md](04_payments_and_legal.md) — period close → Stripe Connect disbursement
