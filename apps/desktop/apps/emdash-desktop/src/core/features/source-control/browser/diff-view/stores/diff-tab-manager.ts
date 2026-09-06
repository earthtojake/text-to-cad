import { reaction } from 'mobx';
import type { DiffViewStore } from '@core/features/source-control/api/browser/diff-view/stores/diff-view-store';
import type { PrStore } from '@core/features/source-control/api/browser/stores/pr-store';
import { commitRef } from '@core/primitives/git/api';
import { getPrNumber } from '@core/services/pull-requests/api';
import type { GitCheckoutStore } from '../../stores/git-checkout-store';
import type { DiffTabResource } from './diff-tab-resource';

interface DiffSession {
  gitCheckout: GitCheckoutStore;
  pr: PrStore;
  diffView: DiffViewStore;
}

/**
 * Persistent, workspace-scoped manager for diff tab resources.
 *
 * Replaces DiffTabLifecycleStore. Manages two concerns:
 *
 * 1. **acquire/release** — tracks the live set of DiffTabResources. Resources call
 *    acquire() in their constructor and release() in dispose(). Because restored diff
 *    tabs are constructed during hydrate() (before initialize()), the manager must
 *    exist before the git/PR session is available.
 *
 * 2. **session binding** — bindSession() starts the git-staleness reaction once a
 *    workspace session is available; unbindSession() tears it down on suspend().
 *
 * activeFile sync is owned by DiffTabResource.onActivate(), which reads the current
 * diffView from currentDiffView() — only non-null while a session is bound.
 */
export class DiffTabManager {
  private readonly _resources = new Set<DiffTabResource>();
  private _session: DiffSession | null = null;
  private _staleDisposer: (() => void) | null = null;

  acquire(resource: DiffTabResource): void {
    this._resources.add(resource);
  }

  release(resource: DiffTabResource): void {
    this._resources.delete(resource);
  }

  /** Returns the bound diffView, or null between sessions. Used by onActivate(). */
  currentDiffView(): DiffViewStore | null {
    return this._session?.diffView ?? null;
  }

  /**
   * Bind git/PR/diffView references and start the staleness reaction.
   * Safe to call again after unbindSession() (e.g. task re-provision).
   */
  bindSession(session: DiffSession): void {
    this._session = session;
    this._staleDisposer = reaction(
      () => this._validKeys(session),
      (validKeys) => this._reconcile(session, validKeys),
      { equals: (a, b) => a.size === b.size && [...a].every((k) => b.has(k)) }
    );
  }

  /** Dispose the staleness reaction and clear the session reference. */
  unbindSession(): void {
    this._staleDisposer?.();
    this._staleDisposer = null;
    this._session = null;
  }

  /** Full teardown — call only when the workspace is permanently removed. */
  dispose(): void {
    this.unbindSession();
    this._resources.clear();
  }

  private _validKeys(session: DiffSession): Set<string> {
    const valid = new Set<string>();
    for (const c of session.gitCheckout.unstagedFileChanges) valid.add(`disk:${c.path}`);
    for (const c of session.gitCheckout.stagedFileChanges) valid.add(`staged:${c.path}`);
    for (const r of this._resources) {
      if (r.diffGroup !== 'pr' || r.prNumber == null) continue;
      const matchedPr = session.pr.pullRequests.find((p) => getPrNumber(p) === r.prNumber);
      if (matchedPr) {
        for (const f of session.pr.getFiles(matchedPr).data ?? []) valid.add(`pr:${f.path}`);
      }
    }
    return valid;
  }

  private _reconcile(session: DiffSession, validKeys: Set<string>): void {
    const stale = [...this._resources].filter(
      (r) => r.diffGroup !== 'git' && !validKeys.has(`${r.diffGroup}:${r.path}`)
    );

    for (const resource of stale) {
      const counterpartGroup: 'disk' | 'staged' | null =
        resource.diffGroup === 'disk' ? 'staged' : resource.diffGroup === 'staged' ? 'disk' : null;

      if (counterpartGroup && validKeys.has(`${counterpartGroup}:${resource.path}`)) {
        const changes =
          counterpartGroup === 'staged'
            ? session.gitCheckout.stagedFileChanges
            : session.gitCheckout.unstagedFileChanges;
        const match = changes.find((c) => c.path === resource.path);
        resource.transition(counterpartGroup, commitRef('HEAD'), match?.status);
      } else {
        // Force-close (no user confirmation needed for auto-close on git state change).
        resource.closeSelf();
      }
    }
  }
}
