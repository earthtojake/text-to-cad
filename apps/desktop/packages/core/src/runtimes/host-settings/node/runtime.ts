import { mkdirSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import type { LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, type Cell } from '@emdash/wire/state';
import {
  ConfigModel,
  readConfigFile,
  watchConfigFile,
  type ConfigFileWatcher,
} from '#services/config-model/node';
import { hostSettingsContract } from '../api/contract';
import type { HostSettingsError } from '../api/errors';
import {
  parseHostSettings,
  type HostSettingsState,
  type UpdateHostSettingsInput,
} from '../api/schemas';

/** The single key in the config model — one settings file per host. */
const HOST_KEY = 'host';

export type HostSettingsRuntimeOptions = {
  /** Absolute path of the settings JSON file in the host's emdash data directory. */
  settingsPath: string;
  logger?: Logger;
};

/**
 * Owns the per-host settings file (spec: activation-scripts-via-terminals, host
 * settings): lenient reads through the shared config model, a watcher so
 * out-of-band edits go live without a poll, and a serialized update path that
 * preserves unknown keys in the file.
 */
export class HostSettingsRuntime {
  private readonly settingsPath: string;
  private readonly logger: Logger;
  private readonly stateCell: Cell<HostSettingsState>;
  private readonly model: ConfigModel<HostSettingsState>;
  private readonly watcher: ConfigFileWatcher;
  /** Serializes updates so concurrent writes never tear the file. */
  private writeQueue: Promise<unknown> = Promise.resolve();
  readonly stateHost: LeasedLiveModelProvider<typeof hostSettingsContract.state>;

  constructor(options: HostSettingsRuntimeOptions) {
    this.settingsPath = options.settingsPath;
    this.logger = options.logger ?? noopLogger;
    this.stateCell = cell<HostSettingsState>(
      { settings: {}, parseError: false },
      { name: 'host-settings' }
    );
    this.stateHost = expose(hostSettingsContract.state, {
      current: () => this.stateCell,
    });
    this.model = new ConfigModel<HostSettingsState>({
      read: async (_key, filePath) => {
        const entry = await readConfigFile(filePath, parseHostSettings);
        return { settings: entry.data, parseError: entry.parseError };
      },
      onChanged: (_key, entry) => this.stateCell.set(entry),
    });
    // The watcher needs the directory to exist; the data dir is host-owned, so
    // creating it here is idempotent bootstrap, not a side effect worth deferring.
    mkdirSync(path.dirname(this.settingsPath), { recursive: true });
    this.watcher = watchConfigFile(this.settingsPath, () => {
      void this.refresh().catch((error) => {
        this.logger.warn?.(`host settings refresh failed: ${String(error)}`);
      });
    });
    void this.refresh().catch((error) => {
      this.logger.warn?.(`initial host settings read failed: ${String(error)}`);
    });
  }

  dispose(): void {
    this.watcher.dispose();
    this.model.dispose();
  }

  async get(): Promise<Result<HostSettingsState, HostSettingsError>> {
    const entry = this.model.get(HOST_KEY) ?? (await this.refresh());
    return ok(entry);
  }

  update(input: UpdateHostSettingsInput): Promise<Result<HostSettingsState, HostSettingsError>> {
    const run = this.writeQueue.then(
      () => this.executeUpdate(input),
      () => this.executeUpdate(input)
    );
    this.writeQueue = run.catch(() => undefined);
    return run;
  }

  private async executeUpdate(
    input: UpdateHostSettingsInput
  ): Promise<Result<HostSettingsState, HostSettingsError>> {
    try {
      // Merge into the raw file object — not the parsed model — so keys this
      // version doesn't know about survive the write (forward compatibility).
      // A present-but-broken file can't be merged; the update replaces it.
      let raw: Record<string, unknown> = {};
      try {
        const parsed: unknown = JSON.parse(await readFile(this.settingsPath, 'utf8'));
        if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
          raw = parsed as Record<string, unknown>;
        }
      } catch {
        // Missing or unparseable: start from empty.
      }
      for (const key of ['shellSetup', 'worktreeRoot', 'tmux', 'watcherExclude'] as const) {
        const value = input[key];
        if (value === undefined) continue;
        if (value === null) delete raw[key];
        else raw[key] = value;
      }
      await mkdir(path.dirname(this.settingsPath), { recursive: true });
      await writeFile(this.settingsPath, `${JSON.stringify(raw, null, 2)}\n`, 'utf8');
      return ok(await this.refresh());
    } catch (error) {
      return err({
        type: 'io-failed',
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private refresh(): Promise<HostSettingsState> {
    return this.model.refresh(HOST_KEY, this.settingsPath);
  }
}
