# 02 — Data Contribution Flow and Contributor Payouts

## Scope

End-to-end lifecycle of a snowpack capture from field collection through manual review, acceptance into the training dataset, and contributor payout. Covers novelty scoring, region gating, the review queue, the payout calculation, and the data ownership / deletion policy.

## End-to-end flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  AvApp (field)                                                      │
│  Capture: image + metadata (GPS, timestamp, column/core/segment)    │
│  → device JWT signs the payload                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  TLS, S2S
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AvServ                                                             │
│  Accepts capture for safety-path completeness (paired w/ check-in)  │
│  Forwards capture metadata + signed upload URL to SnowDB            │
│  Does NOT store image bytes long-term                               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SnowDB                                                             │
│  AvApp uploads image bytes directly to object storage (signed URL)  │
│  Writes row to `captures` table: status=`pending_scoring`           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  daily cron, morning
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SnowDB scoring run                                                 │
│  For each capture from prior 24h:                                   │
│    1. Resolve region from GPS → region_policies row                 │
│    2. If region is "saturated" for that day: novelty_score = 0      │
│       else: compute embedding distance to existing dataset          │
│    3. Compute cross_payout_multiplier (10x if near recent rescue)   │
│    4. Write DataLedger row: status=`pending_review`                 │
│  Notify AvApp: "yesterday's captures scored — N eligible for review"│
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  rmdig-ai review queue (RMDig operator)                             │
│  Operator reviews each pending capture:                             │
│    - Accept → DataLedger.status = `earned`, locked for payout       │
│    - Reject → status = `rejected`, reason tagged                    │
│  Contributor sees status update in their dashboard                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  monthly payout period close
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  rmdig-ai monthly payout job                                        │
│  Aggregates `earned` rows, sums per user, calls Stripe Connect      │
│  Marks DataLedger rows `paid_in_period_id`                          │
└─────────────────────────────────────────────────────────────────────┘
```

## Region gating

Payout eligibility is gated by **per-region, per-day data saturation**. The principle: we pay for data that improves the dataset, not for data we already have.

```sql
-- SnowDB
region_policies (
  id                  uuid pk,
  region_geom         geography(polygon),
  region_name         text,
  active_from         timestamptz,
  active_until        timestamptz,        -- null = open-ended
  daily_saturation_n  int default 50,     -- N captures/day before region closes
  base_payout_cents   int default 1,      -- $0.01 default
  max_resamples_per_segment int default 10
)
```

When SnowDB scores yesterday's captures, it looks up each capture's GPS in `region_policies`. If the region already has ≥ `daily_saturation_n` captures for that date, new captures from that region/date are scored `novelty_score = 0` and marked `payout_eligible = false`.

This makes the gating **dynamic**: a region opens for payout when undersupplied, closes once enough data arrives, and may reopen on a future day when conditions change. The contributor sees this in the app: "Your region is currently saturated for today; captures still welcome for safety but will not earn."

## Novelty scoring

For captures in an open region, novelty is computed against the existing HF dataset:

1. Embed the new capture using a frozen feature extractor (likely the snowGAN discriminator features, same backbone AvAI uses — see [AvAI](../../../AvAI/CLAUDE_BOOTSTRAP.md)).
2. Compute average distance to the N nearest captures already in the dataset for that region/season.
3. Higher distance = more novel = eligible. Below a threshold = not novel, `payout_eligible = false` with reason `low_novelty`.

The scoring run records `model_version_scored_against` on every `DataLedger` row, so disputes can be replayed against the exact model version used.

## Manual review (RMDig operator)

After scoring, every eligible capture lands in the **review queue** in the rmdig-ai portal. Only `rmdig_reviewer` or `rmdig_admin` users can access it.

Review UI:
- Streams pending captures (newest first, filterable by region/contributor)
- Shows image, metadata, GPS on a map, novelty score, nearby existing dataset samples for comparison
- Two-button action: **Accept** / **Reject**
- On reject: required dropdown reason + optional free-text note
- Bulk operations: accept-all-for-contributor (after spot check), reject-all-with-reason (e.g., contributor sent obvious spam)

Reject reasons (initial taxonomy, extensible):

| Code | Meaning |
|---|---|
| `too_blurry` | Image not in focus or motion-blurred |
| `not_enough_snow` | Subject is rock, vegetation, or non-snowpack |
| `wrong_subject` | Not a snowpack core / column / segment |
| `bad_lighting` | Underexposed, overexposed, or shadow-occluded |
| `duplicate` | Near-identical to another capture from same session |
| `metadata_mismatch` | GPS or timestamp obviously wrong |
| `out_of_region` | Captured outside any defined region policy |
| `safety_violation` | Captured in conditions that violated safe-collection rules |
| `other` | Free-text required |

The reject reason is shown to the contributor verbatim. Transparency is non-negotiable here — see "Dispute and audit" below.

## Payout calculation

**Base rate (default, per region policy):** $0.01 per accepted image.

**Resample cap:** maximum 10 resampled images count per core/segment. Anything beyond that is accepted into the dataset (if useful) but does not earn.

**Cross-payout multiplier:** if a capture's GPS is within proximity of a recent rescue (see [03_sar_workflow.md](03_sar_workflow.md) for the definition of "near recent rescue"), the rate is multiplied by 10x (or higher per future policy tuning).

```
payout_cents = base_payout_cents 
             × cross_payout_multiplier
             × (1 if within resample cap else 0)
             × (1 if status='earned' else 0)
```

Examples:
- Normal accepted core image, region open: `1 × 1 × 1 × 1` = $0.01
- 11th resample of the same segment: `1 × 1 × 0 × 1` = $0.00 (still accepted into dataset)
- Accepted image 200m from an avalanche site dispatched in last 48h: `1 × 10 × 1 × 1` = $0.10
- Image in a saturated region: gated upstream, never reaches `earned`

All payout math is recorded on the `DataLedger` row so the contributor can audit exactly how their payout was computed. See [05_ledgers.md](05_ledgers.md).

## Cross-payout (avalanche-site bonus)

**Trigger:** capture GPS is within radius R of a `rescue_ledger` entry where `dispatched_at` is within time window T of the capture.

**Default parameters (tunable):**
- R = 500 meters
- T = 48 hours

**Eligibility:** open to any contributor (not restricted to SAR responders). In practice most cross-payouts will go to SAR teams since they're at avalanche sites by virtue of their job, but the bonus is open because backcountry skiers do witness aftermath legitimately.

**Safety policy (mandatory in contributor TOS):**

> Do not approach active or recent avalanche debris fields unless you are trained and equipped for avalanche-zone operations. Re-slides, unstable debris, and buried hazards make these sites genuinely dangerous. The cross-payout bonus is intended for SAR teams already operating on-site and for opportunistic captures from a safe distance — not as an inducement to enter hazardous terrain.

The TOS is shown in the contributor onboarding flow and re-shown the first time a capture qualifies for cross-payout.

## Data ownership and deletion

**Post-payment ownership:**
- Once RMDig pays for an accepted capture, the **image bytes** become RMDig property as purchased goods. No deletion obligation.
- The **contributor linkage** (which user/device produced it) is personally identifiable under GDPR/CCPA and remains subject to anonymization requests.

**Contributor deletion request:**
- Image stays in the dataset.
- `DataLedger` row's `user_id` is replaced with `NULL` and a flag `anonymized_at`. Capture is now attributed to "anonymous contributor."
- Already-issued payouts are not clawed back (payment was for the goods at the time).
- Model weights trained on the capture are not retrained — standard ML industry practice.

**Pre-payment deletion request:**
- Capture is hard-deleted from object storage and `DataLedger`. No payout owed.

**TOS language (to be drafted with lawyer):** must explicitly state that contribution is a sale of goods, that ownership transfers on payment, that linkage anonymization is the deletion remedy post-payment, and that model weights are not retroactively scrubbed.

See [04_payments_and_legal.md](04_payments_and_legal.md) for the tax characterization of these payments.

## Dispute and audit

Every `DataLedger` row is visible to its contributor in the portal, showing:
- Original capture (thumbnail + metadata)
- Status journey with timestamps: `pending_scoring → pending_review → earned/rejected → paid`
- If scored: novelty score and `model_version_scored_against`
- If reviewed: accept/reject + reason
- If paid: period, amount, Stripe payout reference

If a contributor disputes a reject, they can flag the row in the portal. Flags land in a queue for a second-pass review by a different operator. If escalated and overturned, the original reject is preserved (audit trail) and a new row is created with status `earned`.

The ledger is append-only at the database level. Status transitions create new rows, not in-place mutations.

## Open questions

- **Embedding model versioning:** when the snowGAN backbone is retrained (per snowGAN UPGRADES.md fixes), do prior `DataLedger` rows get re-scored? Recommend: no — scoring is point-in-time, but the contributor sees the model version used so they understand context.
- **Region polygon source:** who draws the initial region polygons? Likely RMDig operator, manually, in an admin UI. Could be informed by historical capture density.
- **Saturation reset:** does daily saturation reset at midnight UTC, midnight local, or rolling 24h? Recommend local midnight per region's centroid timezone — most intuitive for contributors.

## Related docs

- [00_platform_architecture.md](00_platform_architecture.md) — service boundaries
- [03_sar_workflow.md](03_sar_workflow.md) — definition of "recent rescue" for cross-payout
- [04_payments_and_legal.md](04_payments_and_legal.md) — Stripe Connect, 1099-K, TOS
- [05_ledgers.md](05_ledgers.md) — `DataLedger` schema
