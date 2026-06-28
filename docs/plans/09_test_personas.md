# 09 — Cross-service E2E test personas

> **Canonical roster for cross-service test identities.** Test fixtures span
> every repo (portal users + roles, AvServ accounts + devices, AvApp test
> users/devices), so the identities that tie them together live here, in the
> neutral planning repo, rather than being owned by one service. Each repo seeds
> its **own** domain's fixtures against these identities; this doc is the shared
> contract so they don't drift.

## Scope

A small roster of stable test identities used by E2E / integration suites across
the platform. Defines the personas, the principle for using them, and how each
repo maps them into its own domain. It is **not** a list of every fixture — only
the cross-service identities that need to agree.

## Why the email is the key

Under identity-direction-B (see [01](01_accounts_and_orgs.md), and AvServ's
identity docs), the **AvServ account is the canonical principal**, keyed by the
verified email the portal maps a user to. So the **email is the cross-service
identity**: the portal seeds a user with that email, AvServ seeds an account for
it, AvApp's test device links to it. Keep the email stable and everything lines
up across services without sharing a database.

## The roster

| Persona | Email | State | Meaning across the platform |
|---|---|---|---|
| **member** | `e2e-device-link@rmdig.test` | verified, no platform role | The default field user — contributor / SAR-org submitter; the one who links a device and **checks out** for a trip. |
| **staff** | `e2e-staff@rmdig.test` | `rmdig_admin` platform role | Platform operator — SAR-org approvals now, capture review later. |
| **invitee** | `e2e-invitee@rmdig.test` | verified, no role | A second plain user, for org-invitation accept flows. |

Passwords are a portal concern (credentials login) and live in
`rmdig-portal/tests/e2e/helpers.ts`; other services don't need them (they
authenticate devices/accounts, not passwords).

**Proposed but not yet seeded** (add when a spec needs one, per Governance
below): `reviewer` (`rmdig_reviewer`), `unverified` (email-gate), `mfa-user`
(TOTP challenge), `oauth-user` (no password), `dispatcher` / second-org-admin
(SAR membership roles).

## The principle that keeps it stable

- **Personas are stable identities.** Role and auth-state, seeded once per run
  (idempotent upsert), read by tests ("sign in as the staff user"). Never mutate
  a persona's role mid-suite.
- **Per-test workflow data is ephemeral.** Devices, check-outs, orgs,
  invitations, etc. are created fresh inside each test and uniquely named, so
  tests can't collide on them — even when the suite runs sequentially. Baking
  mutable workflow state into a shared persona is the thing that causes flakes.

## How each repo maps the roster

- **rmdig-portal** — seeds these as `users` rows (verified) with the listed
  platform roles, in `tests/e2e/global-setup.ts` (roster in `helpers.ts`,
  `E2E_PERSONAS`). Per-test SAR orgs/invitations are created in the spec.
- **AvServ** — seed an `account` per persona email (and a device fixture where a
  device-link / check-out flow needs one). The account email is the join key the
  portal maps to.
- **AvApp** — map test users / device fixtures to these emails so a cross-service
  device-link or check-out/check-in flow uses the same identity end to end.

## Governance

- **Add a new persona here first**, then seed it in the repos that test it. Don't
  invent a one-off email for an existing role in a single repo.
- **Seed only what a spec exercises** — grow the roster with the suites; an unused
  fixture is dead weight.
- **Keep emails on `@rmdig.test`** (a reserved, non-routable TLD) so a fixture can
  never collide with or email a real address.

## Related docs

- [01_accounts_and_orgs.md](01_accounts_and_orgs.md) — user/account model, roles, device linking (why the email is the principal key)
- [06_phase1_migration.md](06_phase1_migration.md) — the Phase 1 build these suites cover
- [08_terminology_reframe.md](08_terminology_reframe.md) — check-out/check-in lifecycle the safety personas exercise
