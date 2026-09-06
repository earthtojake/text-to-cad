import { createEmitter, type Unsubscribe } from '@emdash/shared';
import { makeAutoObservable, observable } from 'mobx';
import type { JsonObject, JsonValue } from '@core/primitives/json/api';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import { modalStore } from '@core/primitives/modals/react/modal-store';
import type { Subject } from '@core/primitives/subjects/api';
import type { FocusView } from '@core/primitives/telemetry/api/telemetry';
import { focusTracker } from '@core/primitives/telemetry/browser/focus-tracker';
import type { ViewRef } from '@core/primitives/views/api';
import { getViewRuntime } from '@core/primitives/views/react';
import type {
  HistoryEntry,
  NavigationParticipant,
  NavigationParticipantHost,
  Resolution,
} from '../api';
import {
  workbenchHistoryMemento,
  type WorkbenchHistoryState,
  type WorkbenchNavigationState,
} from '../api/mementos';
import type { NavigationHistoryStore } from './navigation-history-store';
import { getNavigationHost, type NavigationHost } from './navigation-host';

const MAX_REDIRECTS = 10;

export type NavigationEventKind = 'traversal' | 'refinement' | 'restoration';

export interface NavigationEvent {
  readonly from: ViewRef | undefined;
  readonly to: ViewRef;
  readonly kind: NavigationEventKind;
}

type LegacyNavigationHandle = MementoHandle<WorkbenchNavigationState>;

interface AttachedParticipant {
  readonly participant: NavigationParticipant;
}

interface PendingLocation {
  readonly refKey: string;
  readonly location: JsonValue;
}

export class NavigationStore implements NavigationParticipantHost {
  readonly onDidNavigate = createEmitter<NavigationEvent>();

  private readonly _host: NavigationHost;
  private _currentRef: ViewRef;
  private readonly _lastRefByViewId = observable.map<string, ViewRef>();
  private _historyHandle: MementoHandle<WorkbenchHistoryState> | undefined;
  private _historyUnsubscribe: Unsubscribe | undefined;
  private readonly _participants = new Map<string, AttachedParticipant>();
  private _pendingLocation: PendingLocation | undefined;
  private _rehydrating = false;

  constructor(private readonly _history: NavigationHistoryStore) {
    this._host = getNavigationHost();
    this._currentRef = this._host.homeRef();
    makeAutoObservable<
      NavigationStore,
      | '_host'
      | '_history'
      | '_currentRef'
      | '_historyHandle'
      | '_historyUnsubscribe'
      | '_participants'
      | '_pendingLocation'
      | '_rehydrating'
      | '_lastRefByViewId'
    >(this, {
      _host: false,
      _history: false,
      _currentRef: observable.ref,
      _lastRefByViewId: false,
      _historyHandle: false,
      _historyUnsubscribe: false,
      _participants: false,
      _pendingLocation: false,
      _rehydrating: false,
      onDidNavigate: false,
    });
  }

  get currentRef(): ViewRef {
    return this._currentRef;
  }

  get currentViewId(): string {
    return this._currentRef.viewId;
  }

  attachMemento(
    historyHandle: MementoHandle<WorkbenchHistoryState>,
    legacyHandle?: LegacyNavigationHandle
  ): void {
    if (this._historyHandle) throw new Error('Navigation history memento is already attached');
    this._historyHandle = historyHandle;
    this._historyUnsubscribe = this._history.onDidChange.subscribe(() => this.persistHistory());

    const legacySeed =
      !historyHandle.hasStoredValue && legacyHandle?.hasStoredValue ? legacyHandle : undefined;
    const persisted = legacySeed ? this.seedFromLegacy(legacySeed.value) : historyHandle.value;
    const rehydrated = persisted.entries.map((entry, sourceIndex) => ({
      entry: this.rehydrateEntry(entry),
      sourceIndex,
    }));
    const entries = rehydrated.flatMap(({ entry }) => (entry ? [entry] : []));
    const index =
      rehydrated.filter(
        ({ entry, sourceIndex }) => entry !== undefined && sourceIndex <= persisted.index
      ).length - 1;

    let attached = false;
    this._rehydrating = true;
    try {
      this._history.replace(entries, index);
      this.rebuildLastRefs();

      const current = this._history.current;
      if (!current) {
        this.navigate(this._host.homeRef());
      } else {
        const resolved = this.resolveChain(current.ref);
        if (resolved.key !== current.ref.key) {
          this._history.prune((entry) => entry === current);
          this.navigate(resolved);
        } else {
          this.commit(resolved, 'restoration');
          this.deliverLocation(resolved, current.location);
        }
      }
      attached = true;
    } finally {
      this._rehydrating = false;
      this.persistHistory();
      if (attached && legacySeed) {
        void legacySeed.reset().catch((error: unknown) => {
          this._host.onError('Failed to reset legacy navigation memento:', error);
        });
      }
    }
  }

  navigate(requested: ViewRef): void {
    this.captureCurrentLocation();
    this._pendingLocation = undefined;
    const resolved = this.resolveChain(requested);
    const previousEntry = this._history.current;
    const entry = this.entryFor(
      resolved,
      previousEntry?.ref.key === resolved.key ? previousEntry.location : undefined
    );
    const kind: NavigationEventKind = previousEntry?.key === entry.key ? 'refinement' : 'traversal';
    this._history.record(entry);
    this.commit(resolved, kind);
  }

  lastRefFor(definition: { readonly id: string }): ViewRef | undefined {
    return this._lastRefByViewId.get(definition.id);
  }

  toggleSettings(): void {
    if (this.currentViewId !== this._host.settingsViewId) {
      this.navigate(this._host.settingsRef());
      return;
    }

    const previous = this._history.nearestBefore(
      (entry) => entry.ref.viewId !== this._host.settingsViewId
    );
    this.navigate(previous?.ref ?? this._host.homeRef());
  }

  invalidateSubject(subject: Subject): void {
    const affects = (ref: ViewRef): boolean => {
      const definition = this._host.views.byId(ref.viewId);
      const refSubject = definition?.subject?.(ref.params as never);
      return refSubject?.kind === subject.kind && refSubject.key === subject.key;
    };

    this._history.prune((entry) => affects(entry.ref));
    for (const [viewId, ref] of this._lastRefByViewId) {
      if (affects(ref)) this._lastRefByViewId.delete(viewId);
    }

    if (affects(this._currentRef)) {
      const resolved = this.resolveChain(this._currentRef);
      if (resolved.key === this._currentRef.key) {
        this.navigate(this._host.homeRef());
      } else {
        this.navigate(resolved);
      }
    }
  }

  applyEntry(entry: HistoryEntry): boolean {
    const definition = this._host.views.byId(entry.ref.viewId);
    const ref = definition?.safeRef(entry.ref.params);
    if (!ref) return false;
    const resolved = this.resolveChain(ref);
    if (resolved.key !== ref.key) return false;

    if (!this.deliverLocation(resolved, entry.location)) return false;
    this.commit(resolved, 'restoration');
    return true;
  }

  attachParticipant<TLocation extends JsonValue>(
    ref: ViewRef,
    participant: NavigationParticipant<TLocation>
  ): Unsubscribe {
    const attached: AttachedParticipant = {
      participant: participant as NavigationParticipant,
    };
    this._participants.set(ref.key, attached);

    if (this._pendingLocation?.refKey === ref.key) {
      const restored = participant.restoreLocation(this._pendingLocation.location as TLocation);
      this._pendingLocation = undefined;
      if (restored === false) {
        const current = this._history.current;
        if (current?.ref.key === ref.key) {
          this._history.prune((entry) => entry === current);
          this._history.record(this.entryFor(ref));
        }
      }
    }

    return () => {
      if (this._participants.get(ref.key) === attached) this._participants.delete(ref.key);
    };
  }

  reportLocation(ref: ViewRef, location: JsonValue): void {
    if (this._history.isApplying || ref.key !== this._currentRef.key) return;
    const parsed = this.parseLocation(ref, location);
    if (parsed === undefined) return;

    const entry = this.entryFor(ref, parsed);
    const current = this._history.current;
    if (!current || current.ref.key !== ref.key) return;

    if (current.location === undefined) {
      this._history.annotate(entry);
      this.onDidNavigate.emit({ from: ref, to: ref, kind: 'refinement' });
      return;
    }

    const kind: NavigationEventKind = current.key === entry.key ? 'refinement' : 'traversal';
    this._history.record(entry);
    this.onDidNavigate.emit({ from: ref, to: ref, kind });
  }

  /** Detaches the history subscription. Called when the app scope is disposed (tests/HMR). */
  dispose(): void {
    this._historyUnsubscribe?.();
    this._historyUnsubscribe = undefined;
  }

  private resolveChain(initial: ViewRef): ViewRef {
    let ref = initial;
    const visited = new Set<string>();

    // Detect cycles and also bound non-repeating redirect chains produced from changing params.
    for (let redirects = 0; redirects < MAX_REDIRECTS; redirects++) {
      const cycleKey = `${ref.viewId}:${JSON.stringify(ref.params)}`;
      if (visited.has(cycleKey)) return this._host.homeRef();
      visited.add(cycleKey);

      const contribution = getViewRuntime(ref.viewId);
      const resolve = contribution?.runtime.resolve as
        | ((params: JsonObject) => Resolution)
        | undefined;
      const resolution = resolve?.(ref.params) ?? { kind: 'ok' };
      if (resolution.kind === 'ok') return ref;
      ref = resolution.ref;
    }

    return this._host.homeRef();
  }

  private commit(ref: ViewRef, kind: NavigationEventKind): void {
    const from = this._currentRef;
    const viewChanged = from.viewId !== ref.viewId;
    if (viewChanged) {
      const viewId = ref.viewId as FocusView;
      focusTracker.transition(
        viewId === 'task'
          ? { view: viewId }
          : { view: viewId, mainPanel: null, focusedRegion: null },
        'navigation'
      );
    }

    this._currentRef = ref;
    this._lastRefByViewId.set(ref.viewId, ref);
    this.onDidNavigate.emit({ from, to: ref, kind });
    if (kind !== 'refinement') modalStore.dismissAll('navigation');
  }

  private entryFor(ref: ViewRef, location?: JsonValue): HistoryEntry {
    const definition = this._host.views.byId(ref.viewId);
    const locationKey =
      location !== undefined && definition?.location
        ? definition.location.key(location as never)
        : undefined;
    return {
      ref,
      ...(location === undefined ? {} : { location }),
      key: locationKey ? `${ref.key}:${locationKey}` : ref.key,
    };
  }

  private parseLocation(ref: ViewRef, location: unknown): JsonValue | undefined {
    const contract = this._host.views.byId(ref.viewId)?.location;
    if (!contract) return undefined;
    const parsed = contract.schema.safeParse(location);
    return parsed.success ? parsed.data : undefined;
  }

  private captureCurrentLocation(): void {
    const participant = this._participants.get(this._currentRef.key);
    if (!participant) return;
    const location = participant.participant.captureLocation();
    if (location === undefined) return;
    const parsed = this.parseLocation(this._currentRef, location);
    if (parsed === undefined) return;
    const current = this._history.current;
    if (current?.ref.key === this._currentRef.key) {
      this._history.annotate(this.entryFor(this._currentRef, parsed));
    }
  }

  private deliverLocation(ref: ViewRef, location: JsonValue | undefined): boolean {
    if (location === undefined) {
      this._pendingLocation = undefined;
      return true;
    }
    const parsed = this.parseLocation(ref, location);
    if (parsed === undefined) return true;

    const participant = this._participants.get(ref.key);
    if (participant) {
      return participant.participant.restoreLocation(parsed) !== false;
    }
    this._pendingLocation = { refKey: ref.key, location: parsed };
    return true;
  }

  private rehydrateEntry(
    persisted: WorkbenchHistoryState['entries'][number]
  ): HistoryEntry | undefined {
    const definition = this._host.views.byId(persisted.viewId);
    const ref = definition?.safeRef(persisted.params);
    if (!ref) return undefined;
    const location =
      persisted.location === undefined ? undefined : this.parseLocation(ref, persisted.location);
    return this.entryFor(ref, location);
  }

  private seedFromLegacy(legacy: WorkbenchNavigationState): WorkbenchHistoryState {
    const params = legacy.viewParams[legacy.currentViewId] ?? {};
    return {
      ...workbenchHistoryMemento.default,
      entries: [{ viewId: legacy.currentViewId, params }],
      index: 0,
    };
  }

  private rebuildLastRefs(): void {
    this._lastRefByViewId.clear();
    for (const entry of this._history.entries.slice(0, this._history.index + 1)) {
      this._lastRefByViewId.set(entry.ref.viewId, entry.ref);
    }
  }

  private persistHistory(): void {
    if (!this._historyHandle || this._rehydrating) return;
    this._historyHandle.update({
      version: '1',
      entries: this._history.entries.map((entry) => ({
        viewId: entry.ref.viewId,
        params: entry.ref.params,
        ...(entry.location === undefined ? {} : { location: entry.location }),
      })),
      index: this._history.index,
    });
  }
}
