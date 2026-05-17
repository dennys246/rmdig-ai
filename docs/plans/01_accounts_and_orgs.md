# 01 — Accounts, Orgs, and Device Linking

## Scope

User identity, SAR team organization model, role-based access, and the device-to-user linking flow that bridges AvApp (device JWTs) and rmdig-ai (user accounts).

## User types

The portal has **one unified login** but three behavioral profiles, distinguished by what roles a user holds:

| Profile | Has | Sees in portal |
|---|---|---|
| **Contributor** | linked AvApp device(s) | Capture history, payout ledger, contribution dashboard, W-9 / Stripe Connect onboarding |
| **SAR responder** | membership in a SAR org | Alert history, response stats, SAR org workspace |
| **SAR admin** | admin role on a SAR org | All of the above + org settings, Stripe Connect (donations), payout dashboard, member management |
| **RMDig operator** | platform admin role | Review queue (capture accept/reject), policy editor (region gating, payout rates), platform-wide ledger views |

A single user may hold multiple profiles (a SAR responder who also contributes data, etc.). The UI surfaces the appropriate workspace based on roles held, not by forking the login experience.

## Schema (rmdig-ai Postgres)

```sql
-- Individuals
users (
  id              uuid pk,
  email           text unique not null,
  display_name    text,
  created_at      timestamptz default now(),
  email_verified_at timestamptz,
  stripe_account_id text,           -- for receiving contributor payouts
  w9_submitted_at timestamptz       -- nullable; required before payout disbursement above threshold
)

-- Platform roles (sparse — most users have none)
user_platform_roles (
  user_id  uuid references users,
  role     text check (role in ('rmdig_admin', 'rmdig_reviewer')),
  granted_at timestamptz default now(),
  primary key (user_id, role)
)

-- SAR organizations
sar_orgs (
  id              uuid pk,
  name            text not null,
  region          text,                  -- human-readable; GPS polygon stored separately
  region_geom     geography(polygon),    -- PostGIS, defines service area
  created_at      timestamptz default now(),
  stripe_account_id text,                -- for donations + payouts (one per org)
  approved_at     timestamptz,           -- gated; RMDig verifies real SAR organization
  donation_enabled boolean default false
)

-- Org membership with role
org_memberships (
  org_id    uuid references sar_orgs,
  user_id   uuid references users,
  role      text check (role in ('admin', 'dispatcher', 'responder')) not null,
  joined_at timestamptz default now(),
  primary key (org_id, user_id)
)

-- AvApp device claim, links AvServ device_id to a user
device_links (
  device_id   text primary key,    -- matches AvServ.devices.id
  user_id     uuid references users not null,
  claimed_at  timestamptz default now(),
  claim_token_used text             -- the one-time token consumed
)
```

PostGIS is required for `region_geom` (SAR org service areas). This is what powers multi-team alert routing in [03_sar_workflow.md](03_sar_workflow.md).

## SAR org roles

- **admin** — manages org settings, members, Stripe payout account, donation page. Can see full payout dashboard. There must be at least one admin per org.
- **dispatcher** — can see incoming alerts and acknowledge them on behalf of the org. Manages the org's response.
- **responder** — receives alerts, contributes movement data (with consent), files follow-up reports. Default role for new members.

Roles are additive (an admin can also respond). Adopt a "least privilege at invite" stance — invites default to `responder`, and admins promote explicitly.

## Device linking flow

AvApp ships with no user concept by default ([AvApp doc 14](../../../AvApp/docs/plans/14_avserv.md)). Device JWTs from AvServ identify the device, not the human. Linking happens **after** device registration:

```
1. User installs AvApp, completes device registration with AvServ
   → AvApp now holds a device JWT, AvServ has a row in `devices` with no user_id
2. User logs into rmdig-ai portal (or creates account)
3. Portal shows "Link a device" button → generates a one-time claim_token (TTL 5 min)
4. Portal displays the token as both a QR code and a short alphanumeric code
5. User opens AvApp → Settings → "Link to account" → scans QR or types code
6. AvApp POSTs the claim_token + device JWT to rmdig-ai's link endpoint
7. rmdig-ai verifies the token, calls AvServ's S2S endpoint to write user_id onto the device row,
   then writes a row in `device_links` for its own view
8. AvApp shows "Linked to account@email" and unlocks contributor features in the app
```

**Why this shape:**
- Token-on-portal, scanned-by-app keeps the secret transmission user-visible (no silent linking).
- Short alphanumeric fallback handles cases where the camera can't read the QR.
- One-time token + 5 min TTL means a leaked token has minimal blast radius.
- Linking is reversible: user can unlink in either AvApp or the portal, which deletes `device_links` row and clears `devices.user_id` in AvServ.

**Unlinking semantics:**
- The device keeps working for safety-of-life features (check-ins, panic) without a user. This is intentional — never break safety because of an account dispute.
- Pending payouts on captures from that device remain attributed to whoever owned the device at capture time. Future captures from the unlinked device do not earn.

## SAR org onboarding

Higher gate than contributor signup because (a) donations flow to them, (b) payouts flow to them, (c) they receive safety-of-life alerts.

```
1. SAR admin signs up as an individual user (standard email/password or OAuth)
2. Creates SAR org → submits: org name, service area (drawn on map), 
   primary contact, proof of operating status (501c3 letter, county SAR registration, etc.)
3. RMDig operator reviews submission in admin workspace → approves or requests changes
4. On approval: org is marked approved_at, admin can invite members, 
   complete Stripe Connect onboarding (KYC handled by Stripe)
5. Once Stripe Connect is verified: donation page goes live, payouts enabled
```

Manual approval is non-negotiable. SAR alerts are safety-of-life; an unverified "SAR org" receiving real alerts is a critical failure mode.

## Authentication

- **Portal:** session-based auth (NextAuth.js / Auth.js v5). Both email/password and OAuth (Google at launch; Apple to follow).
- **MFA mandatory for all users at public launch.** Contributor and SAR-org accounts will have payouts attached, so account takeover is a direct financial-impact event — not just an inconvenience. Enforced via middleware: any session for an unenrolled user is redirected to `/settings/mfa/enroll` before reaching any other portal route. TOTP + recovery codes.
- **During development and internal soft launch**, MFA is optional with a strong-push banner so test contributors don't trip over enrollment. The mandatory gate flips on at public launch.
- **`rmdig_admin` and `rmdig_reviewer` roles** require MFA from day 1 regardless of launch status — these accounts can approve SAR orgs and accept/reject capture data, so they're high-value targets even before money flows.
- **rmdig-ai → AvServ S2S:** peer-tier JWT, signed with rmdig-ai's peer key, accepted by AvServ as a trusted peer (similar to how AvServ nodes authenticate to each other per AvServ CLAUDE.md).
- **rmdig-ai → SnowDB S2S:** simple shared-secret JWT for v1, peer-tier if SnowDB grows multi-node later.

## Open questions

- **Email verification:** required before linking a device? (recommend yes — otherwise a typo'd email orphans all the contributor's data)
- **Org admin transfer:** what happens if the sole admin of a SAR org becomes inactive? Recommend a 90-day inactivity timer + RMDig operator can transfer admin role on request.
- **Cross-org membership:** can a user be a responder for multiple SAR orgs in adjacent regions? Recommend yes; the schema already supports it. UI defaults to one "active" org at a time.

## Related docs

- [00_platform_architecture.md](00_platform_architecture.md) — service boundaries
- [03_sar_workflow.md](03_sar_workflow.md) — uses `sar_orgs.region_geom` for alert routing
- [04_payments_and_legal.md](04_payments_and_legal.md) — Stripe Connect onboarding details
