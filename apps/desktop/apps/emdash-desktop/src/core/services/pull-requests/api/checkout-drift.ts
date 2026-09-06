/**
 * Derived checkout-drift state for a PR-associated workspace (pr-workspace-model
 * spec, Staleness): the join of the registry-observed head OID with the PR
 * cache's head OID. Purely derived, never persisted; recomputed desktop-side on
 * observation and sync updates.
 *
 * - `unknown` — either side missing (unobserved workspace, no associated PR, PR
 *   not in the cache). Never a false `in-sync`.
 * - `in-sync` — observed head OID equals the cached PR head OID.
 * - `drifted` — they differ, with best-effort detail flags. Ancestry is not
 *   computable desktop-side, so flags are honest nulls when unknowable.
 *
 * `syncedAt` is the PR cache's last-sync stamp (epoch ms): the comparison is
 * only as fresh as the cache ("as of last sync"); null when no stamp is known.
 */
export type PrCheckoutDrift =
  | { kind: 'unknown' }
  | { kind: 'in-sync'; syncedAt: number | null }
  | {
      kind: 'drifted';
      /** Local commits ahead of `@{u}`; null when the tracking ref doesn't resolve. */
      localAhead: boolean | null;
      /** The PR head moved past the checkout; null when local commits could explain the drift. */
      prMoved: boolean | null;
      syncedAt: number | null;
    };
