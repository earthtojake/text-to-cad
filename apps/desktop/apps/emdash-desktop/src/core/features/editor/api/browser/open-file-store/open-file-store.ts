import {
  encodeResourceUri,
  resourceKeyFromFileRef,
  type HostFileRef,
  type ResourceKey,
  type ResourceUri,
} from '@emdash/core/primitives/path/api';
import type { ContentSeamErrorCode, FileContentModel } from '@emdash/core/runtimes/files/api';
import { err, ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import { observe, remote, snapshot, type RemoteModel, type Snapshot } from '@emdash/wire/state';
import { makeObservable, observable, runInAction } from 'mobx';
import { getEditorClient } from '@core/features/editor/api/browser/client';
import { filesWireContract } from '@core/features/files/api';
import { getFilesClient } from '@core/features/files/api/browser/client';
import type { GitRef } from '@core/primitives/git/api';
import { facetSlotKey, type Facet, type FacetHandle, type FacetHandleBinder } from './facet-handle';

/**
 * First-load deadline (spec §4): a load attempt that produced no content state
 * within this window classifies as `error(unavailable)`. Per-attempt and
 * orthogonal to the linger; the subscription stays alive while interest is
 * held, so late content still auto-recovers the entry.
 */
export const FIRST_LOAD_DEADLINE_MS = 10_000;

/**
 * The single content linger (spec §9): started on the last interest release
 * of a facet; on expiry the facet handle and its wire subscription are
 * released together. One named constant for local and remote hosts and every
 * facet kind. The store's wire bindings use `lingerMs: 0` so the generic
 * wire-layer linger never stacks on top of this one.
 */
export const OPEN_FILE_LINGER_MS = 15_000;

/**
 * Debounce for crash-recovery autosave of dirty buffer text (spec §7),
 * harvested from the Monaco model registry's buffer debounce.
 */
export const BUFFER_AUTOSAVE_DEBOUNCE_MS = 2_000;

/** The closed seam-error enum rendered by retryable placeholders (spec §4). */
export type SeamErrorCode = ContentSeamErrorCode;

export type ContentStatus =
  | { kind: 'loading' }
  | { kind: 'ready' }
  | { kind: 'orphaned' }
  | { kind: 'error'; code: SeamErrorCode };

export type SaveFileError =
  | { type: 'not-open' }
  | { type: 'no-etag' }
  | { type: 'conflict' }
  | { type: 'write-failed'; message: string };

/**
 * The observable per-file view consumers get from the store: content status,
 * editing flags on the buffer facet, and facet handles. Tabs and panes own
 * "what is open where"; they consume this and never carry content state.
 */
export interface OpenFileEntry {
  readonly key: ResourceKey;
  /** Current serialized identity (first-seen spelling; updated on re-key). */
  readonly uri: ResourceUri;
  /** File content status, driven by the disk source when one is bound. */
  readonly status: ContentStatus;
  readonly dirty: boolean;
  readonly conflicted: boolean;
  readonly saving: boolean;
  handleFor(facet: Facet): FacetHandle | undefined;
  /** Per-ref readiness of a git snapshot facet (spec §6). */
  gitStatus(ref: GitRef): ContentStatus | undefined;
}

export type OpenFileLease = {
  readonly entry: OpenFileEntry;
  release(): void;
};

const LOADING: ContentStatus = { kind: 'loading' };
const READY: ContentStatus = { kind: 'ready' };
const ORPHANED: ContentStatus = { kind: 'orphaned' };

type ContentRemote = RemoteModel<typeof filesWireContract.content>;
type ContentMember = ReturnType<ContentRemote>;
type WriteInvocation = Awaited<ReturnType<ContentMember['mutations']['write']>>;
type WriteFailure = Extract<WriteInvocation['result'], { success: false }>['error'];

type SourceBinding = {
  scope: Scope;
  member: ContentMember | null;
  deadline: TimerHandle | null;
};

type GitSourceBinding = SourceBinding & {
  ref: GitRef;
  lastText: string | undefined;
};

type FacetSlot = {
  readonly facet: Facet;
  interest: number;
  handle: FacetHandle | null;
  pendingHandle: boolean;
  /** Bumped whenever the slot's handle is reset; stales in-flight creations. */
  epoch: number;
  unsubscribeChange: (() => void) | null;
  lingerTimer: TimerHandle | null;
};

const BUFFER_SLOT = 'buffer';
const DISK_SLOT = 'disk';

class OpenFileEntryImpl implements OpenFileEntry {
  key: ResourceKey;
  uri: ResourceUri;
  status: ContentStatus = LOADING;
  dirty = false;
  conflicted = false;
  saving = false;

  readonly facetHandles = observable.map<string, FacetHandle>([], { deep: false });
  readonly gitStatuses = observable.map<string, ContentStatus>([], { deep: false });

  readonly slots = new Map<string, FacetSlot>();
  diskSource: SourceBinding | null = null;
  readonly gitSources = new Map<string, GitSourceBinding>();

  /** Last content and etag observed from the disk source. */
  lastDiskText: string | undefined;
  lastDiskEtag: string | undefined;
  /** Etag of the disk content the buffer was last synchronized with. */
  baseEtag: string | undefined;
  /** True once the disk content has been readable — gates orphan vs not-found. */
  everReady = false;
  /** Buffer text carried across a re-key, applied once the new handle exists. */
  pendingBufferSeed: string | undefined;
  /** Suppresses buffer change handling while the store itself writes text. */
  applyingStoreEdit = false;
  autosaveTimer: TimerHandle | null = null;

  constructor(key: ResourceKey, uri: ResourceUri) {
    this.key = key;
    this.uri = uri;
    makeObservable(this, {
      key: observable.ref,
      uri: observable.ref,
      status: observable.ref,
      dirty: observable,
      conflicted: observable,
      saving: observable,
    });
  }

  handleFor(facet: Facet): FacetHandle | undefined {
    return this.facetHandles.get(facetSlotKey(facet));
  }

  gitStatus(ref: GitRef): ContentStatus | undefined {
    return this.gitStatuses.get(facetSlotKey({ kind: 'git', ref }));
  }
}

/**
 * The app-global owner of open-file state (spec §4/§7/§9): one instance per
 * app, keyed by ResourceKey, editor-framework-free. Consumers acquire
 * ref-counted interest in a file's facets and observe one entry; all editing
 * policy — dirty tracking, etag preconditions, conflict handling,
 * reload-from-disk, crash-recovery autosave, lifetimes — lives here. Content
 * arrives exclusively through the files domain client; facet handles arrive
 * through the registered {@link FacetHandleBinder}.
 */
export class OpenFileStore {
  private readonly entries = new Map<ResourceKey, OpenFileEntryImpl>();
  private readonly scope = createScope({ label: 'open-file-store' });
  private readonly clock: Clock;
  private binder: FacetHandleBinder | null = null;
  private binderWaiters: Array<(binder: FacetHandleBinder) => void> = [];
  private contentRemotePromise: Promise<ContentRemote> | null = null;

  constructor(options: { clock?: Clock } = {}) {
    this.clock = options.clock ?? systemClock;
  }

  /**
   * Registers the facet-handle implementation (the Monaco binder in
   * production, fakes in tests). Handle creation for already-loaded content
   * is deferred until a binder exists.
   */
  registerBinder(binder: FacetHandleBinder): void {
    this.binder = binder;
    const waiters = this.binderWaiters;
    this.binderWaiters = [];
    for (const resolve of waiters) resolve(binder);
  }

  /**
   * Acquires ref-counted interest in one facet of `ref`'s entry. Spellings
   * that normalize to the same ResourceKey share one entry and one in-flight
   * load. Re-acquiring an errored facet restarts the load attempt — failed
   * loads are never cached.
   */
  acquire(ref: HostFileRef, facet: Facet): OpenFileLease {
    const key = resourceKeyFromFileRef(ref);
    let entry = this.entries.get(key);
    if (!entry) {
      entry = new OpenFileEntryImpl(key, encodeResourceUri(ref));
      this.entries.set(key, entry);
    }

    const slotKey = facetSlotKey(facet);
    let slot = entry.slots.get(slotKey);
    if (!slot) {
      slot = {
        facet,
        interest: 0,
        handle: null,
        pendingHandle: false,
        epoch: 0,
        unsubscribeChange: null,
        lingerTimer: null,
      };
      entry.slots.set(slotKey, slot);
    }
    slot.interest += 1;
    slot.lingerTimer?.dispose();
    slot.lingerTimer = null;

    if (facet.kind === 'git') {
      this.ensureGitSource(entry, slotKey, facet.ref);
      const gitStatus = entry.gitStatuses.get(slotKey);
      const binding = entry.gitSources.get(slotKey);
      if (gitStatus?.kind === 'error' && binding) this.restartGitLoad(entry, slotKey, binding);
    } else {
      this.ensureDiskSource(entry);
      if (entry.status.kind === 'error' && entry.diskSource) {
        this.restartDiskLoad(entry, entry.diskSource);
      }
      this.ensureDiskFacetHandles(entry);
    }

    let released = false;
    const publicEntry: OpenFileEntry = entry;
    return {
      entry: publicEntry,
      release: () => {
        if (released) return;
        released = true;
        this.releaseFacet(entry, slotKey);
      },
    };
  }

  /** The entry for `ref`, if any facet of it is currently retained. */
  peek(ref: HostFileRef): OpenFileEntry | undefined {
    return this.entries.get(resourceKeyFromFileRef(ref));
  }

  /** All entries whose buffer currently has unsaved changes. */
  dirtyEntries(): OpenFileEntry[] {
    return [...this.entries.values()].filter((entry) => entry.dirty);
  }

  /** Saves every dirty buffer; false when any save failed (e.g. a conflict). */
  async saveAllDirty(): Promise<boolean> {
    let allSaved = true;
    for (const entry of this.dirtyEntries()) {
      const result = await this.save(entry);
      if (!result.success) allSaved = false;
    }
    return allSaved;
  }

  /** Discards every dirty buffer by reloading it from disk. */
  discardAllDirty(): void {
    for (const entry of this.dirtyEntries()) this.reloadFromDisk(entry);
  }

  /**
   * Applies a crash-recovery buffer row to an already-open entry (the
   * workspace-open restore flow). User edits made since the entry was opened
   * win over the persisted row; a still-loading buffer takes the row as its
   * seed, applied once the handle exists. Entries that are not open are left
   * alone — their rows apply when a tab opens them.
   */
  hydrateBuffer(ref: HostFileRef, content: string): void {
    const entry = this.entries.get(resourceKeyFromFileRef(ref));
    if (!entry || entry.dirty) return;
    const slot = entry.slots.get(BUFFER_SLOT);
    if (!slot) return;
    const handle = slot.handle;
    if (!handle) {
      entry.pendingBufferSeed = content;
      return;
    }
    if (handle.getText() === content) return;
    this.silentSet(entry, handle, content);
    this.reconcileDirty(entry);
  }

  /**
   * Writes the buffer through the content model's etag-preconditioned write
   * mutation. A stale etag classifies as a conflict: the entry flags
   * `conflicted` and the caller resolves via `{ overwrite: true }` or
   * {@link reloadFromDisk}. A successful save clears the crash-recovery
   * buffer.
   */
  async save(
    entry: OpenFileEntry,
    options: { overwrite?: boolean } = {}
  ): Promise<Result<void, SaveFileError>> {
    const impl = this.entries.get(entry.key);
    if (!impl || impl !== entry) return err({ type: 'not-open' as const });
    const slot = impl.slots.get(BUFFER_SLOT);
    const handle = slot?.handle;
    const binding = impl.diskSource;
    if (!handle || !binding?.member) return err({ type: 'not-open' as const });

    const content = handle.getText();
    const precondition = options.overwrite
      ? ({ kind: 'overwrite' } as const)
      : impl.baseEtag
        ? ({ kind: 'etag', etag: impl.baseEtag } as const)
        : null;
    if (!precondition) return err({ type: 'no-etag' as const });

    runInAction(() => {
      impl.saving = true;
    });
    try {
      const invocation = await binding.member.mutations.write({ content, precondition });
      if (!invocation.result.success) {
        const failure = invocation.result.error;
        if (failure.type === 'etag-mismatch') {
          // No refresh needed: the disk watch pushes the newer content that
          // caused the mismatch (and refresh mid-flight can force a resync
          // that stalls the next mutation's cursor settlement).
          runInAction(() => {
            impl.conflicted = true;
          });
          return err({ type: 'conflict' as const });
        }
        return err({ type: 'write-failed' as const, message: describeWriteError(failure) });
      }
      await invocation.settled;

      const latest = binding.member ? snapshot(binding.member.states.content).value : undefined;
      impl.lastDiskText = content;
      if (latest?.kind === 'text') impl.lastDiskEtag = latest.etag;
      impl.baseEtag = impl.lastDiskEtag;
      runInAction(() => {
        impl.dirty = false;
        impl.conflicted = false;
      });
      impl.autosaveTimer?.dispose();
      impl.autosaveTimer = null;
      const client = await getEditorClient();
      await client.clearBuffer({ uri: impl.uri });
      this.maybeScheduleBufferEviction(impl);
      return ok(undefined);
    } finally {
      runInAction(() => {
        impl.saving = false;
      });
    }
  }

  /**
   * Discards buffer edits by reloading the last-known disk content into the
   * buffer (the "reload / discard" conflict resolution). Clears the dirty and
   * conflicted flags and the crash-recovery buffer.
   */
  reloadFromDisk(entry: OpenFileEntry): void {
    const impl = this.entries.get(entry.key);
    if (!impl || impl !== entry) return;
    const handle = impl.slots.get(BUFFER_SLOT)?.handle;
    if (!handle || impl.lastDiskText === undefined) return;
    this.silentSet(impl, handle, impl.lastDiskText);
    impl.baseEtag = impl.lastDiskEtag;
    runInAction(() => {
      impl.dirty = false;
      impl.conflicted = false;
    });
    impl.autosaveTimer?.dispose();
    impl.autosaveTimer = null;
    const uri = impl.uri;
    void getEditorClient()
      .then((client) => client.clearBuffer({ uri }))
      .catch(() => undefined);
    this.maybeScheduleBufferEviction(impl);
  }

  /**
   * Re-keys an entry after a rename/move (spec §4: refs do not survive
   * renames implicitly — the owner re-keys). Buffer text and dirty state are
   * preserved; the crash-recovery row moves to the new ResourceUri; facet
   * handles and wire subscriptions restart under the new identity.
   */
  async rekey(from: HostFileRef, to: HostFileRef): Promise<void> {
    const oldKey = resourceKeyFromFileRef(from);
    const entry = this.entries.get(oldKey);
    if (!entry) return;
    const newKey = resourceKeyFromFileRef(to);
    const newUri = encodeResourceUri(to);
    if (newKey === oldKey && newUri === entry.uri) return;

    const oldUri = entry.uri;
    const bufferSlot = entry.slots.get(BUFFER_SLOT);
    const dirtyText = entry.dirty && bufferSlot?.handle ? bufferSlot.handle.getText() : undefined;

    if (dirtyText !== undefined) {
      const client = await getEditorClient();
      await client.saveBuffer({ uri: newUri, content: dirtyText });
      await client.clearBuffer({ uri: oldUri });
    }
    if (this.entries.get(oldKey) !== entry) return;

    this.entries.delete(oldKey);
    if (newKey !== oldKey && this.entries.has(newKey)) {
      // The target identity is already open; the moved entry cannot merge into
      // it, so its facets tear down and holders re-acquire under the new key.
      for (const slotKey of [...entry.slots.keys()]) this.teardownSlot(entry, slotKey);
      return;
    }
    this.entries.set(newKey, entry);
    runInAction(() => {
      entry.key = newKey;
      entry.uri = newUri;
      entry.dirty = dirtyText !== undefined;
      entry.conflicted = false;
      entry.status = LOADING;
    });

    entry.pendingBufferSeed = dirtyText;
    entry.autosaveTimer?.dispose();
    entry.autosaveTimer = null;
    entry.lastDiskText = undefined;
    entry.lastDiskEtag = undefined;
    entry.baseEtag = undefined;
    entry.everReady = false;

    for (const slot of entry.slots.values()) this.resetSlotHandle(entry, slot);
    runInAction(() => {
      entry.facetHandles.clear();
    });

    if (entry.diskSource) {
      const binding = entry.diskSource;
      entry.diskSource = null;
      binding.deadline?.dispose();
      void binding.scope.dispose();
    }
    for (const binding of entry.gitSources.values()) {
      binding.deadline?.dispose();
      void binding.scope.dispose();
    }
    entry.gitSources.clear();
    runInAction(() => {
      entry.gitStatuses.clear();
    });

    for (const [slotKey, slot] of entry.slots) {
      if (slot.facet.kind === 'git') this.ensureGitSource(entry, slotKey, slot.facet.ref);
    }
    if (entry.slots.has(BUFFER_SLOT) || entry.slots.has(DISK_SLOT)) {
      this.ensureDiskSource(entry);
    }
  }

  async dispose(): Promise<void> {
    for (const entry of [...this.entries.values()]) {
      for (const slotKey of [...entry.slots.keys()]) this.teardownSlot(entry, slotKey);
    }
    this.entries.clear();
    this.contentRemotePromise = null;
    await this.scope.dispose();
  }

  // ---------------------------------------------------------------------------
  // Wire sources
  // ---------------------------------------------------------------------------

  private bindContentRemote(): Promise<ContentRemote> {
    // lingerMs 0: the store owns the single content linger (spec §9); the
    // generic wire-layer linger must not stack a second window on top.
    this.contentRemotePromise ??= getFilesClient().then((client) =>
      remote(filesWireContract.content, client.content, { scope: this.scope, lingerMs: 0 })
    );
    return this.contentRemotePromise;
  }

  private ensureDiskSource(entry: OpenFileEntryImpl): void {
    if (entry.diskSource) return;
    const scope = this.scope.child(`content:disk:${entry.uri}`);
    const binding: SourceBinding = { scope, member: null, deadline: null };
    entry.diskSource = binding;
    scope.add(() => {
      binding.deadline?.dispose();
    });
    this.setStatus(entry, LOADING);
    this.armDeadline(binding, () => {
      if (entry.diskSource !== binding || entry.status.kind !== 'loading') return;
      this.transitionError(entry, 'unavailable');
    });
    const uri = entry.uri;
    void this.bindContentRemote()
      .then((contentRemote) => {
        if (scope.disposed || entry.diskSource !== binding) return;
        // Retain before dereferencing: with lingerMs 0 an unretained family
        // member is disposed at birth. The retention is released with the
        // binding scope, so handle and subscription go together (spec §9).
        const key = { uri, source: 'disk' as const };
        scope.add(contentRemote.retain(key));
        const member = contentRemote(key);
        binding.member = member;
        observe(member.states.content, (snap) => this.onDiskSnapshot(entry, binding, snap), {
          scope,
          immediate: true,
        });
      })
      .catch(() => {
        if (entry.diskSource === binding) this.transitionError(entry, 'unavailable');
      });
  }

  private onDiskSnapshot(
    entry: OpenFileEntryImpl,
    binding: SourceBinding,
    snap: Snapshot<FileContentModel | undefined>
  ): void {
    if (entry.diskSource !== binding) return;
    if (snap.status === 'error') {
      binding.deadline?.dispose();
      binding.deadline = null;
      this.transitionError(entry, 'unavailable');
      return;
    }
    const value = snap.value;
    if (!value) return;
    binding.deadline?.dispose();
    binding.deadline = null;
    this.applyDiskContent(entry, value);
  }

  /** Restarts a load attempt on an existing binding (re-acquire after error). */
  private restartDiskLoad(entry: OpenFileEntryImpl, binding: SourceBinding): void {
    this.setStatus(entry, LOADING);
    this.armDeadline(binding, () => {
      if (entry.diskSource !== binding || entry.status.kind !== 'loading') return;
      this.transitionError(entry, 'unavailable');
    });
    const member = binding.member;
    if (!member) return;
    void member.states.content
      .refresh()
      .then(() => {
        if (entry.diskSource !== binding) return;
        const value = snapshot(member.states.content).value;
        if (!value) return;
        binding.deadline?.dispose();
        binding.deadline = null;
        this.applyDiskContent(entry, value);
      })
      .catch(() => {
        if (entry.diskSource !== binding || entry.status.kind !== 'loading') return;
        binding.deadline?.dispose();
        binding.deadline = null;
        this.transitionError(entry, 'unavailable');
      });
  }

  private ensureGitSource(entry: OpenFileEntryImpl, slotKey: string, ref: GitRef): void {
    if (entry.gitSources.has(slotKey)) return;
    const scope = this.scope.child(`content:${slotKey}:${entry.uri}`);
    const binding: GitSourceBinding = {
      scope,
      member: null,
      deadline: null,
      ref,
      lastText: undefined,
    };
    entry.gitSources.set(slotKey, binding);
    scope.add(() => {
      binding.deadline?.dispose();
    });
    this.setGitStatus(entry, slotKey, LOADING);
    this.armDeadline(binding, () => {
      if (entry.gitSources.get(slotKey) !== binding) return;
      if (entry.gitStatuses.get(slotKey)?.kind !== 'loading') return;
      this.setGitStatus(entry, slotKey, { kind: 'error', code: 'unavailable' });
    });
    const uri = entry.uri;
    void this.bindContentRemote()
      .then((contentRemote) => {
        if (scope.disposed || entry.gitSources.get(slotKey) !== binding) return;
        const key = { uri, source: { ref } };
        scope.add(contentRemote.retain(key));
        const member = contentRemote(key);
        binding.member = member;
        observe(
          member.states.content,
          (snap) => this.onGitSnapshot(entry, slotKey, binding, snap),
          { scope, immediate: true }
        );
      })
      .catch(() => {
        if (entry.gitSources.get(slotKey) !== binding) return;
        this.setGitStatus(entry, slotKey, { kind: 'error', code: 'unavailable' });
      });
  }

  private onGitSnapshot(
    entry: OpenFileEntryImpl,
    slotKey: string,
    binding: GitSourceBinding,
    snap: Snapshot<FileContentModel | undefined>
  ): void {
    if (entry.gitSources.get(slotKey) !== binding) return;
    if (snap.status === 'error') {
      binding.deadline?.dispose();
      binding.deadline = null;
      this.setGitStatus(entry, slotKey, { kind: 'error', code: 'unavailable' });
      return;
    }
    const value = snap.value;
    if (!value) return;
    binding.deadline?.dispose();
    binding.deadline = null;
    switch (value.kind) {
      case 'text': {
        binding.lastText = value.content;
        this.setGitStatus(entry, slotKey, READY);
        const slot = entry.slots.get(slotKey);
        if (slot?.handle) {
          if (slot.handle.getText() !== value.content) slot.handle.setText(value.content);
        } else {
          this.createFacetHandle(entry, slotKey);
        }
        return;
      }
      case 'binary':
        this.setGitStatus(entry, slotKey, { kind: 'error', code: 'binary' });
        return;
      case 'too-large':
        this.setGitStatus(entry, slotKey, { kind: 'error', code: 'too-large' });
        return;
      case 'unavailable':
        this.setGitStatus(entry, slotKey, { kind: 'error', code: value.code });
        return;
    }
  }

  private restartGitLoad(
    entry: OpenFileEntryImpl,
    slotKey: string,
    binding: GitSourceBinding
  ): void {
    this.setGitStatus(entry, slotKey, LOADING);
    this.armDeadline(binding, () => {
      if (entry.gitSources.get(slotKey) !== binding) return;
      if (entry.gitStatuses.get(slotKey)?.kind !== 'loading') return;
      this.setGitStatus(entry, slotKey, { kind: 'error', code: 'unavailable' });
    });
    const member = binding.member;
    if (!member) return;
    void member.states.content
      .refresh()
      .then(() => {
        if (entry.gitSources.get(slotKey) !== binding) return;
        const current = snapshot(member.states.content);
        if (current.value) this.onGitSnapshot(entry, slotKey, binding, current);
      })
      .catch(() => {
        if (entry.gitSources.get(slotKey) !== binding) return;
        if (entry.gitStatuses.get(slotKey)?.kind !== 'loading') return;
        this.setGitStatus(entry, slotKey, { kind: 'error', code: 'unavailable' });
      });
  }

  private armDeadline(binding: SourceBinding, onExpire: () => void): void {
    binding.deadline?.dispose();
    binding.deadline = this.clock.schedule(FIRST_LOAD_DEADLINE_MS, () => {
      binding.deadline = null;
      onExpire();
    });
  }

  // ---------------------------------------------------------------------------
  // Content application and editing policy
  // ---------------------------------------------------------------------------

  private applyDiskContent(entry: OpenFileEntryImpl, content: FileContentModel): void {
    switch (content.kind) {
      case 'text': {
        entry.lastDiskText = content.content;
        entry.lastDiskEtag = content.etag;
        entry.everReady = true;
        this.setStatus(entry, READY);
        this.ensureDiskFacetHandles(entry);
        this.applyDiskText(entry);
        return;
      }
      case 'binary':
        this.transitionError(entry, 'binary');
        return;
      case 'too-large':
        this.transitionError(entry, 'too-large');
        return;
      case 'unavailable': {
        const code = content.code;
        if (code === 'not-found' && entry.everReady) {
          // Delete events are stat-re-validated by the runtime before the
          // content state reports not-found, so this is a real deletion.
          this.setStatus(entry, ORPHANED);
        } else {
          this.transitionError(entry, code);
        }
        return;
      }
    }
  }

  private transitionError(entry: OpenFileEntryImpl, code: SeamErrorCode): void {
    runInAction(() => {
      entry.status = { kind: 'error', code };
      if (entry.dirty) entry.conflicted = true;
    });
  }

  private setStatus(entry: OpenFileEntryImpl, status: ContentStatus): void {
    runInAction(() => {
      entry.status = status;
    });
  }

  private setGitStatus(entry: OpenFileEntryImpl, slotKey: string, status: ContentStatus): void {
    runInAction(() => {
      entry.gitStatuses.set(slotKey, status);
    });
    this.recomputeGitDerivedStatus(entry);
  }

  /** Entries holding only git facets derive their status from those facets. */
  private recomputeGitDerivedStatus(entry: OpenFileEntryImpl): void {
    if (entry.diskSource) return;
    const statuses = [...entry.gitStatuses.values()];
    if (statuses.length === 0) return;
    const errored = statuses.find((status) => status.kind === 'error');
    const next =
      errored ?? (statuses.some((status) => status.kind === 'loading') ? LOADING : READY);
    this.setStatus(entry, next);
  }

  /** Creates any missing buffer/disk handles once disk content is available. */
  private ensureDiskFacetHandles(entry: OpenFileEntryImpl): void {
    if (entry.lastDiskText === undefined) return;
    this.createFacetHandle(entry, DISK_SLOT);
    this.createFacetHandle(entry, BUFFER_SLOT);
  }

  /**
   * Applies the current disk text to the handles: the mirror always follows;
   * the buffer follows when clean (or already matching) and flags a conflict
   * when dirty against a changed base etag — the policy harvested from the
   * Monaco model registry's disk-update reconciliation.
   */
  private applyDiskText(entry: OpenFileEntryImpl): void {
    const text = entry.lastDiskText;
    if (text === undefined) return;
    const diskHandle = entry.slots.get(DISK_SLOT)?.handle;
    if (diskHandle && diskHandle.getText() !== text) diskHandle.setText(text);

    const bufferHandle = entry.slots.get(BUFFER_SLOT)?.handle;
    if (!bufferHandle) return;
    const matches = bufferHandle.getText() === text;
    if (!entry.dirty || matches) {
      if (!matches) this.silentSet(entry, bufferHandle, text);
      entry.baseEtag = entry.lastDiskEtag;
      runInAction(() => {
        entry.dirty = false;
        entry.conflicted = false;
      });
      this.maybeScheduleBufferEviction(entry);
    } else if (entry.baseEtag !== entry.lastDiskEtag) {
      runInAction(() => {
        entry.conflicted = true;
      });
    }
  }

  private createFacetHandle(entry: OpenFileEntryImpl, slotKey: string): void {
    const slot = entry.slots.get(slotKey);
    if (!slot || slot.handle || slot.pendingHandle) return;
    const initialText =
      slot.facet.kind === 'git' ? entry.gitSources.get(slotKey)?.lastText : entry.lastDiskText;
    if (initialText === undefined) return;

    slot.pendingHandle = true;
    const epoch = slot.epoch;
    const descriptor = {
      uri: entry.uri,
      facet: slot.facet,
      initialText,
      readonly: slot.facet.kind !== 'buffer',
    };
    void this.withBinder()
      .then((binder) => binder.createHandle(descriptor))
      .then((handle) => {
        if (entry.slots.get(slotKey) !== slot || slot.epoch !== epoch) {
          handle.dispose();
          return;
        }
        slot.pendingHandle = false;
        slot.handle = handle;
        runInAction(() => {
          entry.facetHandles.set(slotKey, handle);
        });
        if (slot.facet.kind === 'buffer') {
          slot.unsubscribeChange = handle.onDidChange(() => this.onBufferChanged(entry));
          entry.baseEtag = entry.lastDiskEtag;
          const seed = entry.pendingBufferSeed;
          if (seed !== undefined) {
            entry.pendingBufferSeed = undefined;
            this.silentSet(entry, handle, seed);
            this.reconcileDirty(entry);
          }
          this.applyDiskText(entry);
        } else if (slot.facet.kind === 'disk') {
          const text = entry.lastDiskText;
          if (text !== undefined && handle.getText() !== text) handle.setText(text);
        } else {
          const text = entry.gitSources.get(slotKey)?.lastText;
          if (text !== undefined && handle.getText() !== text) handle.setText(text);
        }
      })
      .catch(() => {
        if (entry.slots.get(slotKey) !== slot || slot.epoch !== epoch) return;
        slot.pendingHandle = false;
        // A binder failure degrades to an error placeholder instead of
        // wedging the entry (spec §7).
        if (slot.facet.kind === 'git') {
          this.setGitStatus(entry, slotKey, { kind: 'error', code: 'unavailable' });
        } else {
          this.transitionError(entry, 'unavailable');
        }
      });
  }

  private withBinder(): Promise<FacetHandleBinder> {
    if (this.binder) return Promise.resolve(this.binder);
    return new Promise((resolve) => {
      this.binderWaiters.push(resolve);
    });
  }

  private onBufferChanged(entry: OpenFileEntryImpl): void {
    if (entry.applyingStoreEdit) return;
    this.reconcileDirty(entry);

    entry.autosaveTimer?.dispose();
    entry.autosaveTimer = this.clock.schedule(BUFFER_AUTOSAVE_DEBOUNCE_MS, () => {
      entry.autosaveTimer = null;
      if (!entry.dirty) return;
      const handle = entry.slots.get(BUFFER_SLOT)?.handle;
      if (!handle) return;
      const uri = entry.uri;
      const content = handle.getText();
      void getEditorClient()
        .then((client) => client.saveBuffer({ uri, content }))
        .catch(() => undefined);
    });
  }

  private reconcileDirty(entry: OpenFileEntryImpl): void {
    const handle = entry.slots.get(BUFFER_SLOT)?.handle;
    if (!handle || entry.lastDiskText === undefined) return;
    const dirty = handle.getText() !== entry.lastDiskText;
    runInAction(() => {
      entry.dirty = dirty;
      if (!dirty) entry.conflicted = false;
    });
    if (!dirty) entry.baseEtag = entry.lastDiskEtag;
  }

  private silentSet(entry: OpenFileEntryImpl, handle: FacetHandle, text: string): void {
    if (handle.getText() === text) return;
    entry.applyingStoreEdit = true;
    try {
      handle.setText(text);
    } finally {
      entry.applyingStoreEdit = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Lifetimes
  // ---------------------------------------------------------------------------

  private releaseFacet(entry: OpenFileEntryImpl, slotKey: string): void {
    const slot = entry.slots.get(slotKey);
    if (!slot) return;
    slot.interest = Math.max(0, slot.interest - 1);
    if (slot.interest > 0) return;
    this.scheduleSlotEviction(entry, slotKey, slot);
  }

  private scheduleSlotEviction(entry: OpenFileEntryImpl, slotKey: string, slot: FacetSlot): void {
    // Dirty buffers never evict; eviction is re-evaluated on save/discard.
    if (slotKey === BUFFER_SLOT && entry.dirty) return;
    // Failed loads are never cached: error and orphaned state drops on last
    // release instead of lingering.
    const facetStatus = slot.facet.kind === 'git' ? entry.gitStatuses.get(slotKey) : entry.status;
    if (facetStatus?.kind === 'error' || facetStatus?.kind === 'orphaned') {
      this.teardownSlot(entry, slotKey);
      return;
    }
    slot.lingerTimer?.dispose();
    slot.lingerTimer = this.clock.schedule(OPEN_FILE_LINGER_MS, () => {
      slot.lingerTimer = null;
      if (slot.interest > 0) return;
      if (slotKey === BUFFER_SLOT && entry.dirty) return;
      this.teardownSlot(entry, slotKey);
    });
  }

  /** Restarts the linger for a buffer whose dirty pin was lifted at zero interest. */
  private maybeScheduleBufferEviction(entry: OpenFileEntryImpl): void {
    const slot = entry.slots.get(BUFFER_SLOT);
    if (!slot || slot.interest > 0 || slot.lingerTimer || entry.dirty) return;
    this.scheduleSlotEviction(entry, BUFFER_SLOT, slot);
  }

  /**
   * Releases a facet's handle and wire subscription together; drops the entry
   * when its last facet goes.
   */
  private teardownSlot(entry: OpenFileEntryImpl, slotKey: string): void {
    const slot = entry.slots.get(slotKey);
    if (!slot) return;
    entry.slots.delete(slotKey);
    slot.lingerTimer?.dispose();
    slot.lingerTimer = null;
    this.resetSlotHandle(entry, slot);
    runInAction(() => {
      entry.facetHandles.delete(slotKey);
    });

    if (slot.facet.kind === 'git') {
      const binding = entry.gitSources.get(slotKey);
      entry.gitSources.delete(slotKey);
      if (binding) {
        binding.deadline?.dispose();
        void binding.scope.dispose();
      }
      runInAction(() => {
        entry.gitStatuses.delete(slotKey);
      });
    } else {
      if (slotKey === BUFFER_SLOT) {
        entry.autosaveTimer?.dispose();
        entry.autosaveTimer = null;
      }
      if (!entry.slots.has(BUFFER_SLOT) && !entry.slots.has(DISK_SLOT) && entry.diskSource) {
        const binding = entry.diskSource;
        entry.diskSource = null;
        binding.deadline?.dispose();
        void binding.scope.dispose();
        if (entry.slots.size > 0) this.recomputeGitDerivedStatus(entry);
      }
    }

    if (entry.slots.size === 0) this.entries.delete(entry.key);
  }

  /** Disposes a slot's handle and stales any in-flight handle creation. */
  private resetSlotHandle(entry: OpenFileEntryImpl, slot: FacetSlot): void {
    slot.epoch += 1;
    slot.pendingHandle = false;
    slot.unsubscribeChange?.();
    slot.unsubscribeChange = null;
    slot.handle?.dispose();
    slot.handle = null;
  }
}

function describeWriteError(failure: WriteFailure): string {
  return JSON.stringify(failure);
}

/**
 * The app-global instance (spec §4): one per app, never per workspace, so the
 * same file opened from two workspaces — or from outside any workspace —
 * shares one entry. File tabs acquire buffer+disk facets from it on mount.
 */
export const openFileStore = new OpenFileStore();
