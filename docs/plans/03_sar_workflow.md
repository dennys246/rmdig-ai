# 03 — SAR Workflow and Payouts

## Scope

End-to-end SAR org workflow from alert dispatch through response, follow-up reporting, and monthly payout. Covers multi-team attribution, the standby + response pay model, location-based response signals, the CAIC-modeled follow-up report, donations, and the cross-payout pipeline that pulls SAR teams into the data contribution loop.

## Alert dispatch flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  AvServ watchdog (per CLAUDE.md §11)                                │
│  Detects: check-in overdue past grace period, or panic event        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Routing                                                            │
│  Resolve user's last-known GPS → find sar_orgs whose region_geom    │
│  contains that point. All matching orgs are notified (multi-team).  │
│  dispatch_dedup_key generated; cross-node dedup ensures one logical │
│  dispatch per alert even with AvServ fan-out.                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Per-org notification                                               │
│  Each SAR org's dispatcher(s) + responders receive the alert        │
│  (SMS via Twilio, push to SAR-app surface, optional email)          │
│  Alert payload: user identifier (limited), last-known GPS,          │
│  check-in context, severity, RescueLedger entry id                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Response signals (recorded per-org, per-responder)                 │
│  1. Org ack (dispatcher acknowledges org has received it)           │
│  2. Responder movement (sustained convergence toward last-known)    │
│  3. Resolve (rescue concluded — outcome recorded)                   │
│  4. Follow-up report filed (CAIC-modeled + RMDig fields)            │
└─────────────────────────────────────────────────────────────────────┘
```

## Multi-team attribution

When an alert fires and the user's last-known GPS falls inside multiple SAR orgs' `region_geom`, **all matching orgs are notified equally**.

Attribution for payout:
- All notified orgs receive equal **dispatch credit** (used for transparency, not pay — see "Payout structure" below).
- **Response credit** is weighted per org by engagement tier (see next section). An org that acked + moved + resolved + reported earns full response credit; an org that did nothing earns zero.

The `dispatch_dedup_key` from AvServ's cross-node ledger is reused for payout attribution. This solves two problems at once:
1. AvServ won't double-alert contacts when both nodes' watchdogs fire (existing safety property).
2. RMDig won't double-pay orgs when both nodes attribute the dispatch (new payout property).

## Response engagement tiers

Per discussion, **activation pay is dropped**. The model is standby + response only. Within response, three engagement tiers:

| Tier | Signal | Credit weight |
|---|---|---|
| **Ack only** | Org dispatcher marked "received" but no movement, no resolve | Minimal (e.g., 0.1×) |
| **Ack + movement** | At least one responder showed sustained GPS convergence toward last-known | Standard (1.0×) |
| **Ack + movement + resolve + report** | Above + alert resolved + CAIC-modeled report filed | Full (1.5×) |

This shape pays for **effort**, not for **notification**. The movement signal is the lever that prevents gaming via ack-and-do-nothing; the report bonus pays for the auditable closure.

## Movement signal — what counts and what doesn't

Tracking SAR responder GPS for payout attribution is **opt-in per responder**, disclosed during org onboarding and in the responder app's settings. A responder who declines tracking can still earn standard response credit via the org dispatcher's ack + the post-incident report (manual attestation), but loses the movement-tier auto-detection.

**Algorithm requirements:**

- **Sustained convergence**, not a single ping. Require decreasing distance to last-known over N consecutive pings (e.g., N=3 over 10 minutes).
- **Velocity-bounded** to filter out incidental travel. Lower bound (e.g., 3 km/h, walking) rules out being parked; upper bound is generous (helicopter/snowmobile, ~250 km/h) and intentionally vehicle-agnostic.
- **Effort-relative**, not absolute proximity. Credit distance traveled toward the target, not just ending close. A team based 2 miles away that didn't move earns less than a team 50 miles away that closed to 5.
- **Connectivity-tolerant**. SAR responders will go into the same low-signal terrain as the lost user. Last ping before connectivity loss is treated as the engagement waypoint; the follow-up report closes the loop on re-emergence.
- **Audit-visible**. Each responder can see their recorded location history for the month in the portal. If they dispute a missed signal, they can flag it and an operator can investigate.

## Follow-up report (CAIC-modeled)

The follow-up report is required for the full-credit tier. It is structured (not free text) and modeled after the [Colorado Avalanche Information Center (CAIC) accident report format](https://avalanche.state.co.us/observations) with RMDig-specific extensions.

**Core CAIC-aligned fields:**

| Field | Type |
|---|---|
| Date and time of incident | datetime |
| Location (GPS + descriptive) | geography + text |
| Activity at time of incident | enum (backcountry ski/snowboard, snowmobile, snowshoe, climbing, lift-access OB, other) |
| Party size | int |
| Party experience level | enum (novice/intermediate/advanced/professional) |
| Avalanche involvement | bool; if true, the avalanche subform |
| Avalanche characteristics | size (R/D scale), type (loose dry, slab, wet, etc.), trigger (natural, skier, snowmobile, etc.), slope angle, aspect, elevation |
| Snowpack observations | weak layer, recent loading, recent precip |
| Weather observations | temp, wind, precip, visibility |
| Outcome | found_alive / found_injured / found_deceased / not_found / user_self_resolved |
| Search/rescue details | duration, personnel deployed, agencies involved, location actually found (if differs from last known) |
| Free text notes | text |

**RMDig extensions:**

| Field | Type | Purpose |
|---|---|---|
| `rescue_ledger_id` | uuid fk | Links back to the dispatching alert |
| `sar_org_id` | uuid fk | Filing org |
| `filed_by_user_id` | uuid fk | Responder who filed |
| `responders_present` | uuid[] | Other responders for cross-attribution |
| `cross_payout_opportunity` | bool | Did responders collect snowpack captures on site? (drives data-side cross-payout flow) |
| `data_publish_consent` | enum (none, anonymized, full) | Permission to publish anonymized incident in public avalanche education datasets |

A report becomes the system's authoritative record of the incident. It also becomes data — anonymized incident records are genuinely valuable for avalanche education and could feed back into AvAI training in later phases.

## Cross-payout opportunity (SAR data collection)

This is the bridge between SAR work and the contributor data pipeline. SAR teams on-site at an avalanche have natural access to the highest-value data the dataset can include — real ground-truth conditions captured during an active incident.

When a follow-up report flags `cross_payout_opportunity = true`, responders are prompted in the app to collect snowpack captures with the standard AvApp capture flow. These captures flow through the normal data pipeline (see [02_data_contribution.md](02_data_contribution.md)) but are automatically GPS-gated for the 10x cross-payout multiplier because they're within range of an active `rescue_ledger` entry.

**Important:** the cross-payout flows through `DataLedger`, not `RescueLedger`. SAR teams are paid for collected data the same way contributors are. This keeps the incentive structures cleanly separated:

- **Rescue work** is paid through standby + response (RescueLedger).
- **Data collection during rescue** is paid through the contributor pipeline at the boosted rate (DataLedger with cross-payout multiplier).

No risk of an org being incentivized to want alerts for the rescue payout — rescue pay is just response work — but every alert opens a high-value data-collection opportunity if the team has bandwidth.

## Payout structure

Two pools, governed by different funding sources:

**Standby pool (fixed, monthly):**
- Funded from RMDig's **operating costs** line, not from the profit-share pool.
- Each approved SAR org receives a fixed monthly retainer for being on the dispatch list.
- Retainer amount tunable per region (rural regions covering more area may receive higher retainers; this is a policy question for later).
- Standby pay is predictable income for SAR orgs — doesn't fluctuate with revenue or with how many incidents occurred.

**Response pool (variable, monthly):**
- Funded from the **profit-share pool**: revenue − operating costs (incl. standby retainers) − reserves = pool.
- Distributed across SAR orgs by **percentile of weighted response credit** that month.
- Each org's weight = sum of (engagement_tier_weight) for each alert they were attributed to.
- Org with more weighted credit gets a larger slice of the pool.

```
For each SAR org in period P:
  weight[org] = Σ (engagement_tier_weight[alert] for alert in P attributed to org)
  
total_weight = Σ weight[org] across all orgs
pool_share[org] = (weight[org] / total_weight) × response_pool[P]
```

Worked example for a month with response_pool = $5,000 and 3 orgs:
- Org A: 12 weighted credits (mix of full + standard tiers)
- Org B: 5 weighted credits
- Org C: 1 weighted credit (one ack-only)
- Total: 18 weighted credits
- A gets $5000 × 12/18 = $3,333
- B gets $5000 × 5/18 = $1,389
- C gets $5000 × 1/18 = $278

This sits on top of standby retainers (fixed).

## Donations

SAR orgs may opt into accepting donations via the public portal once Stripe Connect onboarding is complete and `donation_enabled = true` is set.

- Donations flow **directly** through Stripe Connect to the org's connected account.
- RMDig is not a custodian — the money never lands in RMDig's accounts.
- Stripe Connect's standard fees apply.
- Org admins can set a donation page description, a target/goal, and a public donor wall (opt-in per donor).
- Donor receives a Stripe receipt; whether donations are tax-deductible depends on the org's 501(c)(3) status, which is the org's responsibility to display correctly. See [04_payments_and_legal.md](04_payments_and_legal.md).

## Open questions

- **Standby retainer amount:** what's the actual monthly figure per org? Recommend deferring until you have 3-5 orgs onboarded and can size based on real coverage costs.
- **Inactive org standby:** if an org doesn't respond to any alerts for N months, does standby continue? Recommend a 6-month threshold + RMDig operator review before suspending retainer.
- **Cross-org credit splitting:** if Org A acks and Org B actually resolves, how is credit split? Current model gives each org credit for what it did (A gets ack-tier credit, B gets full-tier credit). Total credit is higher than a single-org rescue, which is intentional — multi-team coordination cost is real and should be compensated.
- **Inter-agency rescues:** if county SAR, state SAR, and air rescue are all involved, the report should list all agencies, but only those who are RMDig SAR orgs participate in the payout. The report still captures the full picture for the public record.

## Related docs

- [00_platform_architecture.md](00_platform_architecture.md) — service boundaries
- [01_accounts_and_orgs.md](01_accounts_and_orgs.md) — `sar_orgs.region_geom` powers alert routing
- [02_data_contribution.md](02_data_contribution.md) — cross-payout flows through `DataLedger`
- [04_payments_and_legal.md](04_payments_and_legal.md) — Stripe Connect for donations and payouts
- [05_ledgers.md](05_ledgers.md) — `RescueLedger` schema, dispatch_dedup_key
- [AvServ CLAUDE.md §9](../../../AvServ/CLAUDE.md) — alert dispatch API contract
