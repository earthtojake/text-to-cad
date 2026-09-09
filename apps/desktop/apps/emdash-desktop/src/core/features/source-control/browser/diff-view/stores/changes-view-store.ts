import { computed, makeObservable, observable, reaction, runInAction, when } from 'mobx';
import { type PrStore } from '@core/features/source-control/api/browser/stores/pr-store';
import { type GitCheckoutStore } from '../../stores/git-checkout-store';

export type SelectionState = 'all' | 'none' | 'partial';

export interface ExpandedSections {
  unstaged: boolean;
  staged: boolean;
  pullRequests: boolean;
}

/**
 * Task-scoped persistence seam for the section-expansion fact. `undefined`
 * means the task has never persisted an expansion state, so the store seeds
 * a sensible initial one after the first git load. Backed by the
 * `tasks.diff-preferences` memento in production.
 */
export interface ExpandedSectionsPersistence {
  readonly value: ExpandedSections | undefined;
  set(next: ExpandedSections): void;
}

const ALL_EXPANDED: ExpandedSections = { unstaged: true, staged: true, pullRequests: true };

export class ChangesViewStore {
  unstagedSelection = observable.set<string>();
  stagedSelection = observable.set<string>();

  private _disposeReactions: Array<() => void> = [];
  private _suppressAutoExpand = new Set<keyof ExpandedSections>();

  constructor(
    private readonly gitCheckout: GitCheckoutStore,
    private readonly pr: PrStore,
    private readonly sections: ExpandedSectionsPersistence
  ) {
    makeObservable(this, {
      expandedSections: computed,
      unstagedSelectionState: computed,
      stagedSelectionState: computed,
    });

    // Prune stale paths from selections whenever the file lists change.
    this._disposeReactions.push(
      reaction(
        () => ({
          unstaged: this.gitCheckout.unstagedFileChanges.map((c) => c.path),
          staged: this.gitCheckout.stagedFileChanges.map((c) => c.path),
        }),
        ({ unstaged, staged }) => {
          const unstagedSet = new Set<string>(unstaged);
          const stagedSet = new Set<string>(staged);
          runInAction(() => {
            for (const p of this.unstagedSelection) {
              if (!unstagedSet.has(p)) this.unstagedSelection.delete(p);
            }
            for (const p of this.stagedSelection) {
              if (!stagedSet.has(p)) this.stagedSelection.delete(p);
            }
          });
        }
      )
    );

    // Once the first git load completes: seed a sensible initial expansion for
    // tasks that have never persisted one (a persisted value wins), then start
    // the auto-expand/collapse reaction. Starting it only after the load means
    // the initial counts transition (0 → N) can never override persisted state.
    this._disposeReactions.push(
      when(
        () => !this.gitCheckout.isLoading && !this.gitCheckout.error,
        () => {
          if (this.sections.value === undefined) {
            const hasUnstaged = this.gitCheckout.unstagedFileChanges.length > 0;
            const hasStaged = this.gitCheckout.stagedFileChanges.length > 0;
            const hasPullRequests = this.pr.pullRequests.length > 0;

            this.setSections({
              unstaged: hasUnstaged || (!hasStaged && !hasUnstaged && !hasPullRequests),
              staged: hasStaged,
              pullRequests: hasPullRequests,
            });
          }
          this.startAutoExpandReaction();
        }
      )
    );
  }

  get expandedSections(): ExpandedSections {
    return this.sections.value ?? ALL_EXPANDED;
  }

  /** Auto-collapse when a section empties; auto-expand when it gains entries from zero. */
  private startAutoExpandReaction(): void {
    this._disposeReactions.push(
      reaction(
        () => ({
          unstaged: this.gitCheckout.unstagedFileChanges.length,
          staged: this.gitCheckout.stagedFileChanges.length,
          pullRequests: this.pr.pullRequests.length,
        }),
        (curr, prev) => {
          const next = { ...this.expandedSections };
          let changed = false;

          if (curr.unstaged === 0 && prev.unstaged > 0) {
            next.unstaged = false;
            changed = true;
          } else if (curr.unstaged > 0 && prev.unstaged === 0) {
            if (this._suppressAutoExpand.has('unstaged')) {
              this._suppressAutoExpand.delete('unstaged');
            } else {
              next.unstaged = true;
              changed = true;
            }
          }

          if (curr.staged === 0 && prev.staged > 0) {
            next.staged = false;
            changed = true;
          } else if (curr.staged > 0 && prev.staged === 0) {
            if (this._suppressAutoExpand.has('staged')) {
              this._suppressAutoExpand.delete('staged');
            } else {
              next.staged = true;
              changed = true;
            }
          }

          if (curr.pullRequests === 0 && prev.pullRequests > 0) {
            next.pullRequests = false;
            changed = true;
          } else if (curr.pullRequests > 0 && prev.pullRequests === 0) {
            if (this._suppressAutoExpand.has('pullRequests')) {
              this._suppressAutoExpand.delete('pullRequests');
            } else {
              next.pullRequests = true;
              changed = true;
            }
          }

          if (changed) this.setSections(next);
        }
      )
    );
  }

  /** Single write path for the expansion fact — everything persists through it. */
  private setSections(next: ExpandedSections): void {
    runInAction(() => this.sections.set(next));
  }

  get unstagedSelectionState(): SelectionState {
    const total = this.gitCheckout.unstagedFileChanges.length;
    const selected = this.unstagedSelection.size;
    if (total === 0 || selected === 0) return 'none';
    if (selected === total) return 'all';
    return 'partial';
  }

  get stagedSelectionState(): SelectionState {
    const total = this.gitCheckout.stagedFileChanges.length;
    const selected = this.stagedSelection.size;
    if (total === 0 || selected === 0) return 'none';
    if (selected === total) return 'all';
    return 'partial';
  }

  toggleUnstagedItem(path: string): void {
    if (this.unstagedSelection.has(path)) {
      this.unstagedSelection.delete(path);
    } else {
      this.unstagedSelection.add(path);
    }
  }

  toggleAllUnstaged(): void {
    if (this.unstagedSelectionState === 'all') {
      this.unstagedSelection.clear();
    } else {
      for (const c of this.gitCheckout.unstagedFileChanges) {
        this.unstagedSelection.add(c.path);
      }
    }
  }

  removeUnstagedSelection(paths: readonly string[]): void {
    for (const path of paths) {
      this.unstagedSelection.delete(path);
    }
  }

  toggleStagedItem(path: string): void {
    if (this.stagedSelection.has(path)) {
      this.stagedSelection.delete(path);
    } else {
      this.stagedSelection.add(path);
    }
  }

  toggleAllStaged(): void {
    if (this.stagedSelectionState === 'all') {
      this.stagedSelection.clear();
    } else {
      for (const c of this.gitCheckout.stagedFileChanges) {
        this.stagedSelection.add(c.path);
      }
    }
  }

  removeStagedSelection(paths: readonly string[]): void {
    for (const path of paths) {
      this.stagedSelection.delete(path);
    }
  }

  toggleExpanded(section: keyof ExpandedSections): void {
    this.setSections({
      ...this.expandedSections,
      [section]: !this.expandedSections[section],
    });
  }

  /** Semantic collapse command — the target of the drag-below-threshold path. */
  collapseSection(section: keyof ExpandedSections): void {
    if (!this.expandedSections[section]) return;
    this.setSections({ ...this.expandedSections, [section]: false });
  }

  setExpanded(next: ExpandedSections | ((prev: ExpandedSections) => ExpandedSections)): void {
    this.setSections(typeof next === 'function' ? next(this.expandedSections) : next);
  }

  expandForActiveFileType(group: 'disk' | 'staged' | 'git' | 'pr'): void {
    const section = group === 'disk' ? 'unstaged' : group === 'staged' ? 'staged' : 'pullRequests';
    if (!this.expandedSections[section]) {
      this.setSections({ ...this.expandedSections, [section]: true });
    }
  }

  suppressNextAutoExpand(section: keyof ExpandedSections): void {
    this._suppressAutoExpand.add(section);
  }

  dispose(): void {
    for (const dispose of this._disposeReactions) dispose();
    this._disposeReactions = [];
  }
}
