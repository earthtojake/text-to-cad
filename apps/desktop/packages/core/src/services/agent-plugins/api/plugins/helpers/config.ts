import { parse, stringify } from 'smol-toml';
import type { z } from 'zod';
import type { PluginFs } from '#primitives/plugin-fs/api';

export interface ConfigFile<T> {
  read(fs: PluginFs, path: string): Promise<T>;
  write(fs: PluginFs, path: string, data: T): Promise<void>;
  update(fs: PluginFs, path: string, updater: (current: T) => T): Promise<void>;
}

export function jsonConfig<T>(schema: z.ZodType<T>, defaultValue: T): ConfigFile<T> {
  return {
    async read(fs, path) {
      const content = await fs.read(path);
      if (!content) return defaultValue;
      const parsed = JSON.parse(content);
      return schema.parse(parsed);
    },
    async write(fs, path, data) {
      schema.parse(data); // validate before write
      await fs.write(path, JSON.stringify(data, null, 2) + '\n');
    },
    async update(fs, path, updater) {
      const current = await this.read(fs, path);
      const updated = updater(current);
      await this.write(fs, path, updated);
    },
  };
}

export function tomlConfig<T>(schema: z.ZodType<T>, defaultValue: T): ConfigFile<T> {
  return {
    async read(fs, path) {
      const content = await fs.read(path);
      if (!content) return defaultValue;
      const parsed = parse(content);
      return schema.parse(parsed);
    },
    async write(fs, path, data) {
      schema.parse(data);
      await fs.write(path, stringify(data as Record<string, unknown>));
    },
    async update(fs, path, updater) {
      const current = await this.read(fs, path);
      const updated = updater(current);
      await this.write(fs, path, updated);
    },
  };
}
