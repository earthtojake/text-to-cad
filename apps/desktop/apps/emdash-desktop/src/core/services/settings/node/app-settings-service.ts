import { EventEmitter } from 'node:events';
import type { SettingsContributionMap } from '@core/primitives/settings/api';
import type { AppDb } from '@core/services/app-db/node/db';
import type { AppSettings, AppSettingsKey } from '../api';
import { SettingsStore } from './settings-store';

export class AppSettingsService {
  private readonly events = new EventEmitter();

  constructor(private readonly store: SettingsStore) {}

  get<K extends AppSettingsKey>(key: K): Promise<AppSettings[K]> {
    return this.store.get(key);
  }

  getAll(): Promise<AppSettings> {
    return this.store.getAll();
  }

  getWithMeta<K extends AppSettingsKey>(key: K) {
    return this.store.getWithMeta(key);
  }

  async update<K extends AppSettingsKey>(key: K, value: AppSettings[K]): Promise<void> {
    await this.store.update(key, value);
    this.events.emit('app-settings:changed', key);
  }

  async reset<K extends AppSettingsKey>(key: K): Promise<void> {
    await this.store.reset(key);
    this.events.emit('app-settings:changed', key);
  }

  async resetField<K extends AppSettingsKey>(key: K, field: keyof AppSettings[K]): Promise<void> {
    await this.store.resetField(key, field);
    this.events.emit('app-settings:changed', key);
  }

  initialize(): Promise<void> {
    return this.store.initialize();
  }

  on(event: 'app-settings:changed', listener: (key: AppSettingsKey) => void): void {
    this.events.on(event, listener);
  }

  off(event: 'app-settings:changed', listener: (key: AppSettingsKey) => void): void {
    this.events.off(event, listener);
  }
}

export function createAppSettingsService(options: {
  db: AppDb;
  contributions: SettingsContributionMap<AppSettings>;
}): AppSettingsService {
  return new AppSettingsService(new SettingsStore(options.db, options.contributions));
}
