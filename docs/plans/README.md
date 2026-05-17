# rmdig-ai Platform Plans

Working design docs for refactoring the current Flask marketing site into the user-facing portal of a four-service platform spanning safety operations, snowpack data curation, and ML training.

**Status:** planning phase. No implementation has begun. The current Flask site at `rmdig-ai/app.py` remains live and unchanged.

**Companion projects:**
- [AvServ](../../../AvServ) — Go safety watchdog (deployed)
- [AvApp](../../../AvApp) — Flutter field client (v1.5 in progress)
- [AvAI](../../../AvAI) — transfer-learning library (Phase 3 of 6)
- [snowGAN](../../../snowGAN) — pretraining backbone (bug-fix pass pending)

## Read order

Recommended reading order for a first pass:

| # | Doc | What it answers |
|---|---|---|
| 00 | [Platform architecture](00_platform_architecture.md) | Four-service split, responsibilities, why the boundaries are where they are |
| 01 | [Accounts and orgs](01_accounts_and_orgs.md) | User model, SAR org model, roles, device-linking flow |
| 02 | [Data contribution](02_data_contribution.md) | Capture → score → review → payout flow, region gating, cross-payout |
| 03 | [SAR workflow](03_sar_workflow.md) | Alert dispatch, engagement tiers, follow-up reports, SAR payouts |
| 04 | [Payments and legal](04_payments_and_legal.md) | Stripe Connect, taxes, data ownership, GDPR/CCPA, profit-share math |
| 05 | [Ledgers](05_ledgers.md) | `DataLedger` and `RescueLedger` schemas, period close, audit surface |
| 06 | [Phase 1 migration](06_phase1_migration.md) | Concrete build plan: Flask → Next.js portal with auth, device linking, SAR onboarding |
| 07 | [Portal bootstrap](07_portal_bootstrap.md) | Day-one execution brief for the new `rmdig-portal` repo — to be moved there as `CLAUDE_BOOTSTRAP.md` |

## Key decisions captured here

These are the conclusions from the design conversation that produced these docs. Each links to its primary doc for full reasoning.

- **Four-service split, not a monolith.** rmdig-ai (portal) / AvServ (safety) / SnowDB (data curation, new) / AvAI+snowGAN (training). The safety watchdog stays narrow; user accounts and payouts never enter its hot path. ([00](00_platform_architecture.md))
- **Migrate rmdig-ai to Next.js.** Flask + Jinja can't comfortably host the dashboards, review queue, and map interfaces this is growing into. Migration happens at a new `app.rmdig.ai` subdomain; the marketing site is left in place until the portal is stable. ([00](00_platform_architecture.md))
- **Unified login with role-based workspace.** Contributors, SAR responders, SAR admins, and RMDig operators all log in the same way; the UI surfaces the right workspace based on roles held. ([01](01_accounts_and_orgs.md))
- **SAR orgs are first-class with PostGIS regions.** Multi-team alert routing is GPS-polygon-based. Org onboarding requires manual approval — safety-of-life alerts are not getting routed to unverified orgs. ([01](01_accounts_and_orgs.md), [03](03_sar_workflow.md))
- **Device linking is a one-time claim-token flow.** AvApp keeps working without a user; linking unlocks contributor features. Unlinking never breaks safety. ([01](01_accounts_and_orgs.md))
- **Data scoring runs daily in SnowDB, not in AvServ.** AvServ accepts captures and forwards; SnowDB scores them on a morning cron against the current region-gating policy. Contributors learn next-day whether yesterday's captures earned. ([02](02_data_contribution.md))
- **Manual review queue in the portal.** Every scored-eligible capture is human-reviewed before payout. Reject reasons are surfaced verbatim to contributors. ([02](02_data_contribution.md))
- **Region gating closes saturated regions/days dynamically.** Per-region daily saturation cap; once met, further captures from that region/day don't earn (still accepted for safety). ([02](02_data_contribution.md))
- **Cross-payout: 10x for captures near recent rescues.** GPS + time-window gated; open to any contributor but TOS strongly discourages non-SAR civilians from chasing avalanche aftermath. ([02](02_data_contribution.md), [03](03_sar_workflow.md))
- **Contributor pay is characterized as goods purchase.** Reduces direct 1099 burden; Stripe Connect handles 1099-K filing above threshold. TOS language must support this framing. ([04](04_payments_and_legal.md))
- **W-9 is friction-lite.** Capture and earn without it; Stripe Connect Express required before disbursement above ~$400 cumulative annual. ([04](04_payments_and_legal.md))
- **Post-payment data ownership transfers to RMDig.** Image bytes are RMDig property after payment; contributor linkage can be anonymized on request; model weights are not retrained on deletion. ([02](02_data_contribution.md), [04](04_payments_and_legal.md))
- **SAR pay = standby + response. No activation pay.** Standby is a fixed monthly retainer from operating costs (predictable income). Response is from the variable profit pool, weighted by engagement tier. ([03](03_sar_workflow.md))
- **Engagement tiers measure effort, not notification.** Ack-only (minimal), ack+movement (standard), ack+movement+resolve+report (full). Movement is GPS-based, opt-in per responder, vehicle-agnostic, effort-relative. ([03](03_sar_workflow.md))
- **Follow-up reports are CAIC-modeled.** Structured form aligned with the Colorado Avalanche Information Center accident report format, plus RMDig extensions for rescue-ledger linkage and cross-payout flagging. ([03](03_sar_workflow.md))
- **Donations route directly Stripe-to-Stripe.** SAR orgs hold their own Stripe Connect accounts; RMDig is not a money custodian. Each org's donation page displays its own tax status. ([03](03_sar_workflow.md), [04](04_payments_and_legal.md))
- **Ledgers are append-only and owner-visible.** Every payout decision is auditable by the user/org affected, with model version, region policy version, and engagement tier weights all stored on the row. ([05](05_ledgers.md))
- **Monthly payout periods drive both ledgers.** Period close on the 1st of the following month, disbursement 3-5 business days later. ([05](05_ledgers.md))

## What's not yet decided

These are explicitly flagged in the docs as open questions worth resolving before or during implementation:

- Standby retainer amount per SAR org (defer until 3-5 orgs onboarded)
- Cross-org admin transfer mechanics on inactivity
- Saturation reset cadence (UTC midnight vs local)
- Standard for SAR org approval (county, state, 501c3, etc.) — lawyer + insurance broker to advise
- Insurance scope (E&O, cyber liability)
- International contributor support (likely v2)
- Inter-agency rescue payout splitting for non-RMDig agencies involved in same incident
- Late-arriving follow-up report bonus rules
- Pool reserve percentage for dispute holdback
- Embedding model versioning on backbone retrain — re-score history or not?

## What's being built first

[06_phase1_migration.md](06_phase1_migration.md) is the concrete Phase 1 plan: stand up the Next.js portal at `app.rmdig.ai` with auth, device linking, and SAR org onboarding. Five sub-milestones (P1.0 – P1.5), no capture review or payouts yet — those come in later phases once SnowDB exists and Stripe Connect is approved. Most Phase 1 work is independent of AvServ/AvApp; the device-link flow requires a small AvServ endpoint to be added in parallel.

[07_portal_bootstrap.md](07_portal_bootstrap.md) is the day-one execution brief. Move it to the new `rmdig-portal` repo as `CLAUDE_BOOTSTRAP.md` when you initialize it — it captures architectural constraints, stack versions, accounts to provision, first-day commands, and acceptance criteria for each Phase 1 sub-milestone.

## Doc maintenance

- These docs are working drafts. Update them as decisions change rather than letting them go stale.
- When implementation begins, schemas in [05](05_ledgers.md) will move from this directory into the actual service repos (`SnowDB/migrations/`, `AvServ/migrations/`, `rmdig-ai/migrations/`) and the documents here should link to the canonical schemas rather than duplicate them.
- Legal items in [04](04_payments_and_legal.md) need lawyer sign-off before any payment flow ships. Replace "working stance" language with "approved" language once counsel signs.
