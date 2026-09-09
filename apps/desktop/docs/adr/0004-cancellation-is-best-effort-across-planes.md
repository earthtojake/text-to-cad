# Cancellation is best-effort across planes

> **Retired by ADR 0006.** The outbox and its pending desktop records no longer exist, so
> there is no desktop-local `cancelled` state to define. What remains of this ADR's reasoning:
> forget-host and "Untrack anyway" purge deletion intent without host confirmation, an
> in-flight create cancels via the RPC signal, and orphaned host effects still surface through
> the observation plane (adoption) — never silently lost.

A desktop cancellation settles the desktop record immediately, without waiting for the host to
confirm. `cancelled` on the desktop means "I stopped asking" — not "it didn't happen." If the
intent already reached an unreachable host, the host may run the operation to completion
anyway; that **orphaned host execution is permitted by design**, and its outcome re-enters the
desktop through the ordinary observation path (scan and registry reconciliation) on
reconnection, never silently lost.

## Why

The naive faithfulness claim — the desktop record's terminal outcome eventually equals the
host record's — is falsified by cancel-while-disconnected: the desktop settles `cancelled`,
the unreachable host runs to `succeeded`, and the two records disagree forever. Something has
to give, and the alternatives are worse:

- **Holding cancellation pending until host confirmation** lets an unreachable host pin the
  desktop record open indefinitely — holding its claims and blocking every successor operation
  on those resources. That is the wrong trade for an intent ledger, whose job is to never
  block the desktop on host availability.
- **Guaranteeing the host doesn't execute** is physically impossible once the intent has been
  forwarded and the wire is down.

## What faithfulness still means

The single equality claim splits into three checkable properties (assurance inventory,
`bridge.P2`–`P4`):

- **Fabrication-freedom** (safety): when a desktop record settles with an outcome attributed
  to host execution, that outcome is one the host record actually reached. The desktop never
  invents success or failure — `cancelled` is desktop-local by definition, not attributed.
- **Convergence** (liveness): every *non-cancelled* desktop record eventually settles with the
  host record's terminal outcome, under eventual reconnection.
- **Orphan observation** (liveness): a host outcome orphaned by a desktop-local cancellation
  is eventually observed on reconnection — e.g. a worktree created by a cancelled
  `createWorktree` shows up via snapshot and is adopted, not leaked.

## Constraints

- Cancellation toward the host stays best-effort in mechanism too: if the host is reachable,
  the bridge forwards the cancel and the host stops the work at the next stage boundary; the
  desktop does not wait on that round-trip to settle.
- UI copy and downstream consumers must not read `cancelled` as "no effects happened."
  Effects of orphaned execution surface later as observed reality.
- Orphan observation leans on the adoption path, which currently strips provenance; recovering
  provenance for orphaned creations is tracked separately (assurance map, orphan provenance
  recovery).
