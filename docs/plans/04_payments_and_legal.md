# 04 — Payments, Taxes, and Legal

## Scope

How money moves through the platform: Stripe Connect for contributors and SAR orgs, tax characterization of payouts and donations, data ownership policy, GDPR/CCPA stance, and the profit-share math. Most items here are pending a lawyer's review (engaged ~2025-12) and should be treated as the working design, not legal advice.

> **Disclaimer:** Nothing in this document is legal or tax advice. All characterizations need formal counsel sign-off before going live.

## Stripe Connect — why and how

The platform uses **Stripe Connect** for all money flows. The principle: push tax compliance and money-custody burden onto Stripe (and onto the recipient) rather than carrying it ourselves.

**Two flavors of connected account:**

| Account holder | Type | Onboarding | Purpose |
|---|---|---|---|
| Contributor (individual) | Express | Lightweight (email + bank + tax info) | Receives data payouts |
| SAR org (organization) | Standard | Full (org docs, EIN, principals, bank) | Receives donations + response payouts |

**What we get from Stripe:**

- KYC handled by Stripe — RMDig does not collect, store, or process SSN/EIN/banking data.
- 1099-K filing handled by Stripe at the federal threshold (currently $5,000 in 2025, $2,500 in 2026, $600 thereafter — rules keep shifting; lawyer to confirm at launch).
- Direct payment routing — donations to SAR orgs land in the org's Stripe account, never RMDig's. RMDig is not a custodian of other people's money.
- Standard Stripe fees apply per transaction.

**What we still need to do:**

- Display a clear contributor TOS and donor disclosure (see "TOS requirements" below).
- Build the in-portal payout dashboards that show what's owed, what's been paid, and what's pending Stripe onboarding completion.
- Track our internal `DataLedger` and `RescueLedger` so contributors and SAR orgs can audit the math behind each disbursement.

## Contributor payments — characterized as sale of goods

The working characterization: contributor payouts are **purchases of goods** (snowpack image data as a delivered work product), not payments for services.

**Tax implication:** payments for goods purchased from individuals/businesses do not require 1099-NEC filing by the buyer. Vendors of goods are responsible for their own income reporting. Stripe will still file 1099-K for any contributor exceeding the federal threshold via the Stripe payment processor channel.

**Net effect of this characterization:**
- RMDig issues zero 1099s directly.
- Stripe files 1099-K above threshold.
- Contributor's overall tax burden is unchanged (income is income).
- RMDig's compliance burden is substantially reduced.

**Caveat:** "Is data a good or a license to a service" is a genuinely fact-specific legal question. Software/data licensing has sometimes been treated as a service or as a royalty (1099-MISC) depending on terms. The TOS language must clearly support the "goods purchase" framing — terms like "ownership transfers on payment," "delivered work product," "sale and conveyance." Lawyer will refine this language.

## W-9 timing

Contributors can **collect and submit data without a W-9** on file. The portal will:

1. Show projected pending earnings throughout the month regardless of W-9 status.
2. **Block disbursement above a soft threshold** (default $400 cumulative annual earnings) until the contributor completes Stripe Connect Express onboarding (which collects the equivalent tax info).
3. Show a clear in-portal banner once approaching threshold: "Complete tax setup to receive $X in pending earnings."

This lowers friction for casual contributors who may never cross the threshold while ensuring high-earners are tax-compliant before any money moves.

## SAR org payments

SAR org payouts (both standby and response — see [03_sar_workflow.md](03_sar_workflow.md)) flow through the org's Stripe Connect Standard account.

- **Standby** is a fixed monthly retainer payment characterized as a service contract (org is contracted to be on-call). Likely 1099-NEC territory above threshold, but again, Stripe Connect handles this via 1099-K on the payment processor side.
- **Response pay** is similar — payment for services rendered.
- **Donations** land directly in the org account; RMDig is not the payer or recipient.

Org admins are responsible for distributing internal-to-org pay to their members per their own org structure. RMDig does not pay individual SAR responders directly.

## Donations — tax handling

Donations route directly Stripe-to-Stripe with no RMDig custody. Each org's public donation page must display:

- The org's name and EIN (if applicable).
- Whether the org is a registered 501(c)(3) — if yes, donations are tax-deductible to the donor. If not, the page must NOT imply deductibility.
- Stripe's standard receipt is sent to the donor automatically.
- Optionally, the org can configure custom thank-you messaging.

RMDig's role is to provide the platform; the org is responsible for accurate display of its tax status. The org onboarding flow will ask for the org's tax status and surface it on the donation page accordingly.

## Profit-share math

Revenue minus operating costs (including SAR standby retainers) minus reserves equals the profit pool. The pool is split between the data side and the SAR side, then distributed per-contributor or per-org as described in [02_data_contribution.md](02_data_contribution.md) and [03_sar_workflow.md](03_sar_workflow.md).

```
period_revenue
  − period_operating_costs       (infrastructure, salaries, contractor pay)
  − period_sar_standby           (fixed retainers, paid before pool calc)
  − period_reserves              (% set aside for runway/future spending)
  = period_profit_pool

period_profit_pool split:
  → data_pool:    contributor earnings (DataLedger eligible rows in period)
  → response_pool: SAR response payouts (RescueLedger weighted credits in period)
```

The split between `data_pool` and `response_pool` itself is a policy choice. Recommend starting with weighting by aggregate "claimed value":
- `data_pool` = sum of pending `DataLedger` payout amounts for the period (these are already individually priced via $0.01 × multipliers).
- `response_pool` = the remainder of the profit pool.

This means contributors are paid at the rate the policy sets, and SAR teams divide whatever is left. In months with low revenue, response pay shrinks but standby retainers (paid from operating costs) keep SAR orgs whole on baseline.

**Transparency commitment:** publish monthly platform-wide totals (revenue, operating costs, standby paid, reserves, profit pool, data pool, response pool) in the portal. Individual contributor and org income stays private to that user/org. This builds the trust needed for a profit-share model.

## Data ownership and the contributor TOS

Recap from [02_data_contribution.md](02_data_contribution.md):

- **Image bytes**: become RMDig property on payment. No deletion obligation post-payment.
- **Contributor linkage** (which user/device produced what): GDPR/CCPA-eligible personal data. Anonymization on request is the deletion remedy post-payment.
- **Model weights** trained on the data: not retrained on deletion request (industry standard).
- **Pre-payment data**: hard-deleted on request, no payout owed.

The TOS must clearly state all four. Working bullet list for the lawyer:

1. Contribution is a sale of goods; ownership transfers on payment.
2. Payments are made through Stripe Connect; contributor is responsible for own income reporting; Stripe will file 1099-K above threshold.
3. Image bytes are RMDig property after payment and may be used in training, published in research datasets, or otherwise commercialized without further compensation.
4. Contributor identity may be anonymized on request post-payment; the bytes remain.
5. Pre-payment captures may be deleted on request.
6. Model weights derived from contributed data are not subject to deletion or retraining requests.
7. Liability: contributor warrants captures are their own work, not infringing, not staged/falsified. Knowing submission of fraudulent captures voids payment and may be reported.
8. Safety: contributor agrees not to enter avalanche-active terrain unsafely in pursuit of cross-payout bonuses.

## SAR org TOS — additional clauses

On top of the contributor TOS, SAR orgs agree to:

- Accurately represent their operating status and certifications.
- Maintain the capability to respond to alerts within their declared region.
- Honor opt-in location tracking disclosures with their responders.
- File follow-up reports for incidents they were dispatched to.
- Not solicit alerts (no inducement to dispatch).
- Not represent RMDig in legal/public matters without authorization.

## GDPR / CCPA stance

Even though the primary subjects (snow images) are not personal data, the platform handles enough personal data (user accounts, GPS traces, device identifiers, payout records) that we must comply.

**Working stance:**
- Right to access: every user can export their data from the portal (Settings → Download my data).
- Right to anonymize: post-payment, contributor linkage anonymization fulfills deletion for paid captures; full deletion for unpaid captures + account closure.
- Right to portability: data export is machine-readable JSON/CSV.
- Data minimization: don't store more PII than necessary. Notably, do not store SAR responders' precise GPS traces longer than 90 days unless they consent to longer retention for personal record-keeping.

## Open legal questions for counsel (consolidated)

1. **Goods vs. service vs. license** characterization for contributor payments — confirm "goods sale" framing holds, and provide TOS language that supports it.
2. **1099-K threshold transitions** (federal rule keeps shifting) — confirm Stripe Connect handles filing correctly and contributors are informed before threshold.
3. **501(c)(3) verification responsibility** for SAR org donation pages — is RMDig liable if an org misrepresents its tax-deductible status? How to disclaim/protect.
4. **Multi-state nexus** for donations and payouts — does the platform create sales tax or income tax nexus in 50 states + internationally? Likely no for goods purchases but worth confirming.
5. **International contributors** — payouts to non-US contributors via Stripe Connect (e.g., W-8BEN equivalent). Initial scope can be US-only; international is a v2 question.
6. **SAR organization status** — what's the minimum verification standard for an "approved" SAR org? County registration? State certification? Nonprofit status? Lawyer + insurance broker to advise on liability exposure.
7. **Insurance** — what liability coverage does the platform need given safety-of-life alert dispatch? Errors & omissions? Cyber liability? Likely yes to both.
8. **TOS update mechanism** — clickwrap on first login after material changes; track acceptance per user.

## Related docs

- [00_platform_architecture.md](00_platform_architecture.md) — service boundaries
- [02_data_contribution.md](02_data_contribution.md) — DataLedger and contributor flow
- [03_sar_workflow.md](03_sar_workflow.md) — RescueLedger and SAR pay structure
- [05_ledgers.md](05_ledgers.md) — period_id and audit trail design
