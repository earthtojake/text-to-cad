import type { GitObjectRef } from '@emdash/core/runtimes/git/api';
import { action, computed, makeObservable, reaction } from 'mobx';
import type { PrStore } from '@core/features/source-control/api/browser/stores/pr-store';
import type {
  TaskDiffPreferencesState,
  TaskDiffSelectionState,
  ActiveFile,
} from '@core/features/tasks/contributions/mementos';
import { commitRef } from '@core/primitives/git/api';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import { ChangesViewStore } from '../../../../browser/diff-view/stores/changes-view-store';
import { type GitCheckoutStore } from '../../../../browser/stores/git-checkout-store';

export const MAX_STACKED_FILES = 8;

type CommitAction = 'commit' | 'commit-push' | 'commit-pr';

const VALID_OBJECT_REF_KINDS = new Set(['branch', 'commit', 'tag']);

function isValidGitObjectRef(raw: unknown): raw is GitObjectRef {
  return (
    raw !== null &&
    typeof raw === 'object' &&
    VALID_OBJECT_REF_KINDS.has((raw as Record<string, unknown>)['kind'] as string)
  );
}

export class DiffViewStore {
  readonly viewMode = 'file' as const;

  readonly changesView: ChangesViewStore;

  /**
   * Index of the override file within its source list at the time it was set.
   * Used as a position hint when the file disappears so we can select a neighbor
   * rather than always falling back to the first file. Not observable — always
   * updated atomically with activeFileOverride inside setActiveFile.
   */
  private _activeFileOverrideIndex = -1;

  private _disposeReactions: Array<() => void> = [];

  constructor(
    private readonly gitCheckout: GitCheckoutStore,
    private readonly pr: PrStore,
    private readonly preferencesHandle: MementoHandle<TaskDiffPreferencesState>,
    private readonly selectionHandle: MementoHandle<TaskDiffSelectionState>
  ) {
    // Section expansion persists per task on the diff-preferences memento;
    // the adapter keeps ChangesViewStore decoupled from the memento shape.
    this.changesView = new ChangesViewStore(gitCheckout, pr, {
      get value() {
        return preferencesHandle.value.expandedSections;
      },
      set: (next) => {
        preferencesHandle.update((current) => ({ ...current, expandedSections: next }));
      },
    });

    makeObservable<DiffViewStore, 'preferencesHandle' | 'selectionHandle'>(this, {
      activeFileOverride: computed,
      activeFile: computed,
      effectivePrTab: computed,
      diffStyle: computed,
      commitAction: computed,
      prTab: computed,
      setActiveFile: action,
      setDiffStyle: action,
      setPrTab: action,
      preferencesHandle: false,
      selectionHandle: false,
    });

    // Reset PR tab when the current PR changes (different PR URL).
    this._disposeReactions.push(
      reaction(
        () => this.pr.currentPr?.url,
        () => {
          this.setPrTab(this.pr.currentPr?.status === 'open' ? 'files' : 'commits');
        }
      )
    );

    // Auto-expand the changes panel section that contains the newly selected file.
    this._disposeReactions.push(
      reaction(
        () => this.activeFile,
        (file) => {
          if (!file || file.group === 'git' || file.group === 'pr') return;
          this.changesView.expandForActiveFileType(file.group);
        }
      )
    );
  }

  get activeFileOverride(): ActiveFile | null {
    return (this.selectionHandle.value.activeFile as ActiveFile | undefined) ?? null;
  }

  get diffStyle(): 'unified' | 'split' {
    return this.preferencesHandle.value.diffStyle;
  }

  get commitAction(): CommitAction | null {
    return this.preferencesHandle.value.commitAction;
  }

  get prTab(): 'files' | 'commits' | 'checks' {
    return this.preferencesHandle.value.prTab;
  }

  /**
   * The effective active file. Derived from activeFileOverride by validating it
   * against the current working-tree lists. Falls back to a neighbor or the
   * default file when the override is stale. Always consistent with observable
   * state — no reaction needed.
   */
  get activeFile(): ActiveFile | null {
    const override = this.activeFileOverride;
    if (!override) return this._defaultActiveFile;

    // git/pr groups cannot be validated against working-tree lists — trust the override
    if (override.group === 'git' || override.group === 'pr') return override;

    const isStaged = override.group === 'staged';
    const ownList = isStaged
      ? this.gitCheckout.stagedFileChanges
      : this.gitCheckout.unstagedFileChanges;
    const otherList = isStaged
      ? this.gitCheckout.unstagedFileChanges
      : this.gitCheckout.stagedFileChanges;

    // Override is still valid
    if (ownList.some((f) => f.path === override.path)) return override;

    // File moved to the other list (staged/unstaged while active)
    if (otherList.some((f) => f.path === override.path)) {
      return {
        ...override,
        type: isStaged ? 'disk' : 'git',
        group: isStaged ? 'disk' : 'staged',
        originalRef: commitRef('HEAD'),
      };
    }

    // File completely gone — select position-based neighbor within the same group
    const idx = Math.max(0, this._activeFileOverrideIndex);
    const neighbor = ownList[Math.min(idx, ownList.length - 1)];
    if (neighbor) return { ...override, path: neighbor.path };

    // Same-group list is now empty — fall back to first file in the other group
    if (otherList.length > 0) {
      return {
        ...override,
        path: otherList[0]!.path,
        type: isStaged ? 'disk' : 'git',
        group: isStaged ? 'disk' : 'staged',
        originalRef: commitRef('HEAD'),
      };
    }

    return null;
  }

  get effectivePrTab(): 'files' | 'commits' | 'checks' {
    if (this.pr.currentPr?.status !== 'open' && this.prTab === 'files') {
      return 'commits';
    }
    return this.prTab;
  }

  get effectiveCommitAction(): CommitAction {
    if (this.commitAction !== null) return this.commitAction;
    return this.gitCheckout.isPublished ? 'commit-push' : 'commit';
  }

  setCommitAction(action: CommitAction | null): void {
    this.preferencesHandle.update((current) => ({ ...current, commitAction: action }));
  }

  setActiveFile(file: ActiveFile | null): void {
    if (file && !isValidGitObjectRef(file.originalRef)) return;
    this.selectionHandle.update((current) => ({
      ...current,
      activeFile: file ?? undefined,
    }));
    if (file?.group === 'disk' || file?.group === 'staged') {
      const list =
        file.group === 'staged'
          ? this.gitCheckout.stagedFileChanges
          : this.gitCheckout.unstagedFileChanges;
      this._activeFileOverrideIndex = list.findIndex((f) => f.path === file.path);
    } else {
      this._activeFileOverrideIndex = -1;
    }
  }

  setDiffStyle(style: 'unified' | 'split'): void {
    this.preferencesHandle.update((current) => ({ ...current, diffStyle: style }));
  }

  setPrTab(tab: 'files' | 'commits' | 'checks'): void {
    this.preferencesHandle.update((current) => ({ ...current, prTab: tab }));
  }

  dispose(): void {
    for (const dispose of this._disposeReactions) dispose();
    this._disposeReactions = [];
    this.changesView.dispose();
  }

  private get _defaultActiveFile(): ActiveFile | null {
    const first = this.gitCheckout.unstagedFileChanges[0] ?? this.gitCheckout.stagedFileChanges[0];
    if (!first) return null;
    const isUnstaged = !!this.gitCheckout.unstagedFileChanges[0];
    return {
      path: first.path,
      type: isUnstaged ? 'disk' : 'git',
      group: isUnstaged ? 'disk' : 'staged',
      originalRef: commitRef('HEAD'),
    };
  }
}
