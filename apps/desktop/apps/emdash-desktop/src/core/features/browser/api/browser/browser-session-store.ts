import { action, computed, makeObservable, observable } from 'mobx';
import {
  BROWSER_DEFAULT_URL,
  browserPartitionForProfile,
  createBrowserSessionSnapshot,
  makeBrowserSessionIdentity,
  normalizeBrowserProfileSelection,
  normalizeBrowserUrl,
  normalizeBrowserZoomFactor,
  type BrowserLoadError,
  type BrowserProfile,
  type BrowserProfileSelection,
  type BrowserSessionRestoreInput,
  type BrowserSessionSnapshot,
} from '@core/primitives/browser/api';

export type BrowserSessionCreateInput = {
  projectId: string;
  workspaceId: string;
  taskId: string;
  browserId?: string;
  profileId?: BrowserProfileSelection;
  initialUrl?: string;
};

export type BrowserSessionUpdate = Partial<
  Pick<BrowserSessionSnapshot, 'canGoBack' | 'canGoForward' | 'isLoading' | 'title' | 'zoomFactor'>
> & {
  currentUrl?: string;
  faviconUrl?: string | null;
  loadError?: BrowserLoadError | null;
};

export class BrowserSessionStore {
  readonly sessions = observable.map<string, BrowserSessionSnapshot>();

  constructor() {
    makeObservable(this, {
      sessions: observable,
      activeSessions: computed,
      createSession: action,
      restoreSession: action,
      setSessionProfile: action,
      migrateProfileSessions: action,
      updateSession: action,
      removeSession: action,
      clear: action,
    });
  }

  get activeSessions(): BrowserSessionSnapshot[] {
    return Array.from(this.sessions.values());
  }

  createSession(input: BrowserSessionCreateInput): BrowserSessionSnapshot {
    const identity = makeBrowserSessionIdentity(input);
    const snapshot = createBrowserSessionSnapshot({
      identity,
      profileId: input.profileId,
      currentUrl: input.initialUrl,
    });
    this.sessions.set(snapshot.browserId, snapshot);
    return snapshot;
  }

  restoreSession(
    snapshot: BrowserSessionRestoreInput,
    profiles?: readonly BrowserProfile[]
  ): BrowserSessionSnapshot {
    const normalized = normalizeBrowserUrl(snapshot.currentUrl);
    const profileId = normalizeBrowserProfileSelection(snapshot.profileId, profiles);
    const restored: BrowserSessionSnapshot = {
      ...snapshot,
      profileId,
      partition: browserPartitionForProfile(snapshot, profileId),
      currentUrl: normalized.ok ? normalized.url : BROWSER_DEFAULT_URL,
      zoomFactor: normalizeBrowserZoomFactor(snapshot.zoomFactor),
      isLoading: false,
      loadError: undefined,
      updatedAt: Date.now(),
    };
    this.sessions.set(restored.browserId, restored);
    return restored;
  }

  setSessionProfile(
    browserId: string,
    profileId: BrowserProfileSelection,
    profiles?: readonly BrowserProfile[]
  ): BrowserSessionSnapshot | null {
    const existing = this.sessions.get(browserId);
    if (!existing) return null;
    const normalized = normalizeBrowserProfileSelection(profileId, profiles);
    if (normalized === existing.profileId) return existing;
    const next: BrowserSessionSnapshot = {
      ...existing,
      profileId: normalized,
      partition: browserPartitionForProfile(existing, normalized),
      isLoading: false,
      loadError: undefined,
      updatedAt: Date.now(),
    };
    this.sessions.set(browserId, next);
    return next;
  }

  migrateProfileSessions(
    fromProfileId: BrowserProfileSelection,
    toProfileId: BrowserProfileSelection,
    profiles: readonly BrowserProfile[]
  ): void {
    const profileId = normalizeBrowserProfileSelection(toProfileId, profiles);
    for (const [browserId, session] of this.sessions) {
      if (session.profileId !== fromProfileId) continue;
      this.sessions.set(browserId, {
        ...session,
        profileId,
        partition: browserPartitionForProfile(session, profileId),
        isLoading: false,
        loadError: undefined,
        updatedAt: Date.now(),
      });
    }
  }

  updateSession(browserId: string, update: BrowserSessionUpdate): BrowserSessionSnapshot | null {
    const existing = this.sessions.get(browserId);
    if (!existing) return null;

    const normalized =
      update.currentUrl === undefined ? undefined : normalizeBrowserUrl(update.currentUrl);
    const next: BrowserSessionSnapshot = {
      ...existing,
      ...update,
      currentUrl:
        normalized === undefined
          ? existing.currentUrl
          : normalized.ok
            ? normalized.url
            : existing.currentUrl,
      zoomFactor:
        update.zoomFactor === undefined
          ? existing.zoomFactor
          : normalizeBrowserZoomFactor(update.zoomFactor),
      faviconUrl:
        update.faviconUrl === null ? undefined : (update.faviconUrl ?? existing.faviconUrl),
      loadError: update.loadError === null ? undefined : (update.loadError ?? existing.loadError),
      updatedAt: Date.now(),
    };
    this.sessions.set(browserId, next);
    return next;
  }

  getSession(browserId: string): BrowserSessionSnapshot | undefined {
    return this.sessions.get(browserId);
  }

  getSnapshot(browserId: string): BrowserSessionSnapshot | undefined {
    const snapshot = this.sessions.get(browserId);
    return snapshot ? { ...snapshot } : undefined;
  }

  removeSession(browserId: string): void {
    this.sessions.delete(browserId);
  }

  clear(): void {
    this.sessions.clear();
  }
}

export const browserSessionStore = new BrowserSessionStore();
