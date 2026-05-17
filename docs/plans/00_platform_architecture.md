# 00 — Platform Architecture

## Context

`rmdig-ai` is being refactored from a Flask marketing site into the user-facing portal of a four-service platform spanning safety operations, data curation, and ML training. This document captures the architectural split, the reasoning behind it, and the responsibilities of each service.

## The four planes

| Service | Job | Tech | Reliability target |
|---|---|---|---|
| **rmdig-ai** (this repo) | Marketing site, user accounts, SAR org management, dashboards, capture review UI, payouts UI, Stripe integration | Next.js (migration from Flask) + Postgres | Standard web SLO |
| **AvServ** (`~/Scripts/AvServ`) | Safety watchdog: device registration, check-ins, alert dispatch, panic/Send-Help, heartbeat, model manifest distribution | Go + Postgres + Cloudflare Tunnel | 99.9% (CLAUDE.md §10) |
| **SnowDB** (new, to be built) | Capture storage, daily rolling novelty scoring, manual review queue API, region-gating policy table, HF dataset push, `DataLedger` source of truth | TBD (likely Python or Go) + Postgres + object storage | Best-effort batch |
| **AvAI / snowGAN** (`~/Scripts/AvAI`, `~/Scripts/snowGAN`) | Training pipelines: snowGAN pretrains the discriminator backbone; AvAI does transfer learning to predict avalanche metrics; publishes versioned model artifacts to HuggingFace Hub | Python + TensorFlow | Offline batch |

## Why split this way

The split is organized around **failure-domain isolation**, not feature grouping.

- **AvServ must stay narrow.** Its CLAUDE.md is dogmatic about minimal surface area, hardware-backed signing keys, no silent failures, and 99.9% watchdog uptime. Adding OAuth flows, Stripe webhooks, review queue handlers, or embedding-model inference to the same process would degrade the safety SLO. AvServ accepts captures and immediately forwards them to SnowDB; it does not store image bytes long-term.
- **SnowDB owns the data lifecycle.** Novelty scoring needs an embedding model in memory. The review queue serves admin UI traffic with different latency requirements than the watchdog. HF dataset pushes are background batch jobs that can fail and retry without affecting safety. Bundling these into AvServ would make it impossible to operate the watchdog safely; bundling them into rmdig-ai would put image bytes in the portal's hot path.
- **rmdig-ai is the human surface.** Users, SAR orgs, dashboards, review UIs, billing — anywhere a human logs in or money moves. It must not be in the safety-critical path for check-in dispatch.
- **AvAI / snowGAN are offline.** Training runs are not on any request path. They consume from HF, produce to HF, and the only runtime interaction is rmdig-ai/SnowDB reading the published model version manifest.

## Cross-service communication

```
                 ┌──────────────────────────────┐
                 │         User (web)           │
                 └──────────────┬───────────────┘
                                │ HTTPS
                                ▼
       ┌────────────────────────────────────────────┐
       │           rmdig-ai  (Next.js)              │
       │  • accounts, orgs, dashboards              │
       │  • review queue UI, payouts UI, Stripe     │
       └──┬──────────────────┬──────────────────┬───┘
          │  S2S API         │  S2S API         │  HF model manifest
          ▼                  ▼                  ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
  │   AvServ     │   │    SnowDB    │   │  AvAI / snowGAN  │
  │   (Go)       │   │              │   │  (offline batch) │
  │              │   │              │   │                  │
  │ devices,     │   │ captures,    │   │ training runs,   │
  │ check-ins,   │   │ scoring,     │   │ HF Hub push      │
  │ alerts,      │◄──┤ review,      │   │                  │
  │ watchdog     │   │ DataLedger,  │   │                  │
  │              │──►│ HF push      │   │                  │
  └──────┬───────┘   └──────────────┘   └──────────────────┘
         │ TLS                                  ▲
         ▼                                      │
  ┌──────────────┐                              │
  │    AvApp     │──────────────────────────────┘
  │  (Flutter)   │   pulls model manifest from AvServ;
  │              │   loads weights from HF (signed URLs)
  │ field client │
  └──────────────┘
```

**Patterns:**

- **rmdig-ai → AvServ:** server-to-server REST with peer JWT, used for admin views (e.g., list SAR teams' alert history) and device-to-user linking writes. Read-mostly.
- **rmdig-ai → SnowDB:** server-to-server REST for the review queue, ledger views, and accept/reject mutations. Read-write.
- **AvServ → SnowDB:** AvServ forwards capture metadata + signed upload URLs; raw bytes go directly from AvApp to SnowDB object storage.
- **AvServ → AvApp:** existing API surface per AvServ CLAUDE.md §9.

## Database isolation

- **rmdig-ai Postgres:** `users`, `sar_orgs`, `org_memberships`, `device_links`, `payout_periods`, `stripe_account_refs`.
- **AvServ Postgres:** `devices`, `check_ins`, `send_help_events`, `alert_ledger`, `contacts`, `outbox`, `inbox`, `rescue_ledger` (see [05_ledgers.md](05_ledgers.md)).
- **SnowDB Postgres:** `captures`, `review_queue`, `region_policies`, `scoring_runs`, `data_ledger`, `hf_push_log`.

No service has direct DB access to another's tables. All cross-service reads go through the owning service's API. This is non-negotiable — direct DB access across services makes it impossible to evolve schemas independently.

## What is explicitly *not* in scope for any one service

- **rmdig-ai does not** store raw image bytes, dispatch alerts, or hold device signing keys.
- **AvServ does not** host the review queue, run novelty scoring, talk to Stripe, or know about user accounts beyond a `user_id` foreign reference set during device linking.
- **SnowDB does not** dispatch alerts, run training, or process payments.
- **AvAI / snowGAN do not** serve any live request path.

## Migration sequence

The current Flask `rmdig-ai` site remains live during migration. Recommended order:

1. Stand up Next.js skeleton at `app.rmdig.ai` (subdomain) while marketing stays at `rmdig.ai`. See [01_accounts_and_orgs.md](01_accounts_and_orgs.md) for the auth model that goes here first.
2. Stand up SnowDB as its own service with capture ingestion + review queue. See [02_data_contribution.md](02_data_contribution.md).
3. Extend AvServ to forward captures to SnowDB and accept `user_id` on `devices` (coordinated AvApp v1.5 work).
4. Wire payouts last, once Stripe Connect is approved and KYC flows are tested. See [04_payments_and_legal.md](04_payments_and_legal.md).
5. Eventually fold the marketing site into Next.js once the portal is stable, retiring the Flask app.

## Related docs

- [01_accounts_and_orgs.md](01_accounts_and_orgs.md) — user model, SAR org model, device linking
- [02_data_contribution.md](02_data_contribution.md) — capture flow, scoring, review, contributor payouts
- [03_sar_workflow.md](03_sar_workflow.md) — SAR org flow, alerts, response tracking, SAR payouts
- [04_payments_and_legal.md](04_payments_and_legal.md) — Stripe Connect, taxes, data ownership
- [05_ledgers.md](05_ledgers.md) — `DataLedger` and `RescueLedger` schemas
