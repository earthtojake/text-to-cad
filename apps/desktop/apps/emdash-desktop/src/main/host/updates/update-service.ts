import type { Disposable } from '@emdash/shared/concurrency';
import _electronUpdater, {
  type ProgressInfo,
  type UpdateInfo,
  type Logger as UpdaterLogger,
} from 'electron-updater';
import { updateEvents } from '@core/features/updates/node';
import { IS_CANARY, UPDATE_CHANNEL } from '@core/primitives/app-identity/api/app-identity';
import { resolveAppVersion } from '@main/core/app/utils';
import { log } from '@main/lib/logger';
import { formatUpdaterError, isUpdateFeedUnavailable, sanitizeUpdaterLogArgs } from './utils';

let autoUpdater: typeof _electronUpdater.autoUpdater | undefined;

function getAutoUpdater(): typeof _electronUpdater.autoUpdater {
  autoUpdater ??= _electronUpdater.autoUpdater;
  return autoUpdater;
}

const ALLOW_PRERELEASE = IS_CANARY;
const ALLOW_DOWNGRADE = false;
const CHECK_INTERVAL_MS = 60 * 60 * 1000; // 1 hour
const STARTUP_DELAY_MS = 30 * 1000; // 30 seconds
const INSTALL_RESTART_GUARD_TIMEOUT_MS = 2 * 60 * 1000;

export interface UpdateState {
  status: 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'installing' | 'error';
  lastCheck?: Date;
  nextCheck?: Date;
  currentVersion: string;
  availableVersion?: string;
  updateInfo?: UpdateInfo;
  downloadProgress?: {
    bytesPerSecond: number;
    percent: number;
    transferred: number;
    total: number;
  };
  error?: string;
  rollbackVersion?: string;
  releaseNotes?: string;
}

export interface UpdateNotificationPublisher {
  available(version: string): void;
  downloaded(version: string): void;
  error(message: string): void;
}

class UpdateService implements Disposable {
  private updateState: UpdateState;
  private checkTimer?: NodeJS.Timeout;
  private currentCheckPromise: Promise<UpdateInfo | null> | null = null;
  private initialized = false;
  private active = false;
  // Set once a check proves there is no feed to reach; further scheduled checks are skipped so a
  // build that was never published (a fork, a private repo) does not log an error every hour.
  private feedUnavailable = false;
  private installRequested = false;
  private installRestartGuardTimer?: NodeJS.Timeout;
  private notificationPublisher?: UpdateNotificationPublisher;

  constructor() {
    this.updateState = {
      status: 'idle',
      currentVersion: 'unknown',
    };
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    this.initialized = true;

    this.updateState.currentVersion = await resolveAppVersion();

    if (import.meta.env.DEV) return;

    this.setupAutoUpdater();
    this.setupEventListeners();
    this.active = true;

    log.info('AutoUpdateService initialized', {
      version: this.updateState.currentVersion,
      channel: UPDATE_CHANNEL,
    });

    this.scheduleNextCheck(STARTUP_DELAY_MS);
  }

  setNotificationPublisher(publisher: UpdateNotificationPublisher): void {
    this.notificationPublisher = publisher;
  }

  private setupAutoUpdater(): void {
    const autoUpdater = getAutoUpdater();
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.autoRunAppAfterInstall = true;
    autoUpdater.allowPrerelease = ALLOW_PRERELEASE;
    autoUpdater.allowDowngrade = ALLOW_DOWNGRADE;
    autoUpdater.requestHeaders = { 'Cache-Control': 'no-cache' };

    const updaterLogger: UpdaterLogger = {
      info: (...args: unknown[]) => log.debug('[autoUpdater]', ...sanitizeUpdaterLogArgs(args)),
      warn: (...args: unknown[]) => log.warn('[autoUpdater]', ...sanitizeUpdaterLogArgs(args)),
      error: (...args: unknown[]) => log.error('[autoUpdater]', ...sanitizeUpdaterLogArgs(args)),
    };
    autoUpdater.logger = updaterLogger;
  }

  private setupEventListeners(): void {
    const autoUpdater = getAutoUpdater();
    autoUpdater.on('checking-for-update', () => {
      this.updateState.status = 'checking';
      this.updateState.lastCheck = new Date();
      updateEvents.emit(undefined, { type: 'checking' });
    });

    autoUpdater.on('update-available', (info: UpdateInfo) => {
      this.updateState.status = 'available';
      this.updateState.availableVersion = info.version;
      this.updateState.updateInfo = info;
      updateEvents.emit(undefined, { type: 'available', version: info.version });
      this.publishNotification((publisher) => publisher.available(info.version));
    });

    autoUpdater.on('update-not-available', () => {
      this.updateState.status = 'idle';
      updateEvents.emit(undefined, { type: 'not-available' });
    });

    autoUpdater.on('error', (err: Error) => {
      const errorMessage = formatUpdaterError(err);
      if (isUpdateFeedUnavailable(err)) {
        if (!this.feedUnavailable) {
          this.feedUnavailable = true;
          log.warn('Update feed unavailable; skipping further update checks this session', {
            detail: errorMessage,
          });
        }
        this.updateState.status = 'idle';
        this.updateState.error = undefined;
        return;
      }
      log.error('Auto-updater error:', errorMessage);

      if (this.updateState.status === 'installing') {
        log.warn('Ignoring auto-updater error while install is in progress');
        return;
      }

      const previousVersion = this.updateState.availableVersion;
      const previousInfo = this.updateState.updateInfo;

      this.updateState.status = 'error';
      this.updateState.error = errorMessage;

      if (previousVersion) {
        this.updateState.availableVersion = previousVersion;
        this.updateState.updateInfo = previousInfo;
      }

      updateEvents.emit(undefined, { type: 'error', message: errorMessage });
      this.publishNotification((publisher) => publisher.error(errorMessage));
    });

    autoUpdater.on('download-progress', (progressObj: ProgressInfo) => {
      this.updateState.status = 'downloading';
      this.updateState.downloadProgress = {
        bytesPerSecond: progressObj.bytesPerSecond,
        percent: progressObj.percent,
        transferred: progressObj.transferred,
        total: progressObj.total,
      };
      updateEvents.emit(undefined, {
        type: 'progress',
        bytesPerSecond: progressObj.bytesPerSecond,
        percent: progressObj.percent,
        transferred: progressObj.transferred,
        total: progressObj.total,
      });
    });

    autoUpdater.on('update-downloaded', (info: UpdateInfo) => {
      this.updateState.status = 'downloaded';
      this.updateState.rollbackVersion = this.updateState.currentVersion;
      updateEvents.emit(undefined, { type: 'downloaded', version: info.version });
      this.publishNotification((publisher) => publisher.downloaded(info.version));
    });
  }

  private scheduleNextCheck(delay = CHECK_INTERVAL_MS): void {
    if (this.checkTimer) {
      clearTimeout(this.checkTimer);
    }
    if (this.feedUnavailable) {
      this.updateState.nextCheck = undefined;
      return;
    }
    this.updateState.nextCheck = new Date(Date.now() + delay);
    this.checkTimer = setTimeout(() => {
      this.checkForUpdates().catch((e) => {
        log.error('Scheduled update check failed:', e);
      });
    }, delay);
  }

  async checkForUpdates(): Promise<UpdateInfo | null> {
    if (!this.active) return null;
    if (this.currentCheckPromise) return this.currentCheckPromise;

    this.currentCheckPromise = this._performCheck().finally(() => {
      this.currentCheckPromise = null;
      this.scheduleNextCheck();
    });

    return this.currentCheckPromise;
  }

  private async _performCheck(): Promise<UpdateInfo | null> {
    if (this.updateState.status === 'error') {
      this.updateState.status = 'idle';
      this.updateState.error = undefined;
    }

    log.info('Checking for updates...', {
      channel: UPDATE_CHANNEL,
      currentVersion: this.updateState.currentVersion,
    });

    const result = await getAutoUpdater().checkForUpdatesAndNotify();
    return result?.updateInfo ?? null;
  }

  async downloadUpdate(): Promise<void> {
    if (!this.active) throw new Error('Update service is not active');
    if (this.updateState.status === 'error' && this.updateState.availableVersion) {
      this.updateState.status = 'available';
    }

    if (this.updateState.status !== 'available') {
      throw new Error(`Cannot download: status is "${this.updateState.status}", not "available"`);
    }

    if (!this.updateState.availableVersion) {
      throw new Error('No version information available for download');
    }

    this.updateState.status = 'downloading';
    updateEvents.emit(undefined, {
      type: 'downloading',
      version: this.updateState.availableVersion,
    });

    try {
      await getAutoUpdater().downloadUpdate();
    } catch (error: unknown) {
      const errorMessage = formatUpdaterError(error);
      log.error('Update download failed:', errorMessage, error);

      const version = this.updateState.availableVersion;
      const info = this.updateState.updateInfo;

      this.updateState.status = 'error';
      this.updateState.error = errorMessage;
      this.updateState.availableVersion = version;
      this.updateState.updateInfo = info;

      updateEvents.emit(undefined, { type: 'error', message: errorMessage });
      this.publishNotification((publisher) => publisher.error(errorMessage));
      throw error;
    }
  }

  quitAndInstall(): void {
    if (!this.active) throw new Error('Update service is not active');
    if (this.installRequested) {
      log.info('quitAndInstall ignored: install already requested');
      return;
    }

    if (this.updateState.status !== 'downloaded') {
      throw new Error(
        `Cannot install update: status is "${this.updateState.status}", expected "downloaded"`
      );
    }

    this.installRequested = true;
    this.updateState.status = 'installing';
    updateEvents.emit(undefined, { type: 'installing' });

    log.info('Installing update', {
      fromVersion: this.updateState.currentVersion,
      toVersion: this.updateState.availableVersion,
    });

    const clearGuard = () => {
      if (this.installRestartGuardTimer) {
        clearTimeout(this.installRestartGuardTimer);
        this.installRestartGuardTimer = undefined;
      }
    };

    const rollback = (reason: string) => {
      clearGuard();
      this.installRequested = false;
      this.updateState.status = 'downloaded';
      if (this.updateState.availableVersion) {
        updateEvents.emit(undefined, {
          type: 'downloaded',
          version: this.updateState.availableVersion,
        });
        this.publishNotification((publisher) =>
          publisher.downloaded(this.updateState.availableVersion!)
        );
      }
      log.error(reason);
    };

    this.installRestartGuardTimer = setTimeout(() => {
      rollback('quitAndInstall timed out before app quit; allowing retry');
    }, INSTALL_RESTART_GUARD_TIMEOUT_MS);

    setTimeout(() => {
      try {
        getAutoUpdater().quitAndInstall(false, true);
      } catch (error) {
        rollback(`quitAndInstall threw: ${formatUpdaterError(error)}`);
      }
    }, 250);
  }

  async fetchReleaseNotes(): Promise<string | null> {
    try {
      if (!this.updateState.updateInfo) {
        return null;
      }

      const releaseNotes = this.updateState.updateInfo.releaseNotes;
      if (releaseNotes) {
        const normalizedReleaseNotes =
          typeof releaseNotes === 'string'
            ? releaseNotes
            : releaseNotes
                .map((note) => note.note)
                .filter((note): note is string => typeof note === 'string' && note.length > 0)
                .join('\n\n');
        if (normalizedReleaseNotes) {
          this.updateState.releaseNotes = normalizedReleaseNotes;
          return normalizedReleaseNotes;
        }
      }

      const version = this.updateState.availableVersion;
      if (!version) return null;

      const response = await fetch(
        `https://api.github.com/repos/amywork777/hardcore/releases/tags/v${version}`
      );

      if (response.ok) {
        const data = (await response.json()) as { body?: string };
        const notes = data.body || 'No release notes available';
        this.updateState.releaseNotes = notes;
        return notes;
      }

      return null;
    } catch (error) {
      log.error('Failed to fetch release notes:', error);
      return null;
    }
  }

  getState(): UpdateState {
    return { ...this.updateState };
  }

  get isInstallRequested(): boolean {
    return this.installRequested;
  }

  get isActive(): boolean {
    return this.active;
  }

  private publishNotification(publish: (publisher: UpdateNotificationPublisher) => void): void {
    if (!this.notificationPublisher) return;
    try {
      publish(this.notificationPublisher);
    } catch (error) {
      log.warn('Failed to publish update notification', { error });
    }
  }

  dispose(): void {
    if (this.checkTimer) {
      clearTimeout(this.checkTimer);
      this.checkTimer = undefined;
    }
    if (this.installRestartGuardTimer) {
      clearTimeout(this.installRestartGuardTimer);
      this.installRestartGuardTimer = undefined;
    }
  }
}

export const updateService = new UpdateService();
