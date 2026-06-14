# 08 — Terminology reframe: "check out / check in" (platform pointer)

> **Pointer doc — not the source of truth.** The canonical, cross-repo
> plan-of-record lives in **AvServ `docs/plans/08_terminology_reframe.md`**. Read
> that first. This doc records the rmdig-side scope so the platform docs stay in
> lockstep.

## The reframe in one line

The trip-safety lifecycle becomes **check out → check in**: a user *checks out*
when heading into the field (arms a watched outing with an `expected_return_at` +
emergency contact) and *checks in* when safe (closes it, disarms the watchdog). If
they don't check in by `expected_return_at + grace`, the watchdog dispatches the
alert. Same single-deadline mechanism AvServ already implements — only the words
change. "check in" is the one-shot safe confirmation, **not** a periodic ping.

## rmdig scope

- **rmdig-portal: no-op.** It is the identity/account/device-link shell; the
  `/v1/internal/*` contract carries no lifecycle vocabulary. At most one
  descriptive line if any is added later.
- **rmdig-ai docs: 🟢 reference updates only** — `00`/`01`/`02`/`03`/`05`/`07`/
  `README` mention check-ins incidentally; reword to the check-out/check-in model
  when the cross-repo cutover runs (after AvApp C5/C6, before C7).

## Reserved vocabulary (keep the safety terms unambiguous)

- **Heartbeat** = passive device telemetry; never a "check-in" / safety pulse.
- **"ping" / "movement ping"** = reserved for SAR-responder GPS (doc 03). No
  user-safety concept may reuse "ping".
- **"check-out"** must mean exactly one thing platform-wide — disambiguate the
  SAR-routing "check-out" tier (AvApp doc 20) so it does not collide with the new
  user lifecycle verb.

## Pre-existing landmines to fix in the same pass

- **doc 03 stale cross-ref:** it cites "AvServ CLAUDE.md §11" for the watchdog; the
  watchdog is **§7**.
- See AvServ doc 08 §9 for the full landmine list (API hyphen drift, etc.).
