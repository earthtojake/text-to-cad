import { randomUUID } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { dirname, join, resolve, sep } from 'node:path';
import type { PluginFs } from '#primitives/plugin-fs/api';

function isFileNotFoundException(error: unknown): boolean {
  if (!error || typeof error !== 'object' || !('code' in error)) return false;
  const code = (error as { code?: unknown }).code;
  return code === 'ENOENT' || code === 'ENOTDIR';
}

export function createLocalPluginFs(root: string): PluginFs {
  const absRoot = resolve(root);

  function resolveSafe(path: string): string {
    const abs = resolve(join(absRoot, path));
    const rootWithSep = absRoot.endsWith(sep) ? absRoot : absRoot + sep;
    const absWithSep = abs.endsWith(sep) ? abs : abs + sep;
    if (!absWithSep.startsWith(rootWithSep) && abs !== absRoot) {
      throw new Error(`Plugin fs: path escape attempt: ${path}`);
    }
    return abs;
  }

  return {
    async read(path: string): Promise<string | null> {
      try {
        return await fs.readFile(resolveSafe(path), 'utf-8');
      } catch (error: unknown) {
        if (isFileNotFoundException(error)) return null;
        throw error;
      }
    },
    async write(path: string, content: string): Promise<void> {
      const abs = resolveSafe(path);
      await fs.mkdir(dirname(abs), { recursive: true });
      const tmpPath = `${abs}.${randomUUID()}.tmp`;
      try {
        await fs.writeFile(tmpPath, content, 'utf-8');
        await fs.rename(tmpPath, abs);
      } catch (error: unknown) {
        await fs.rm(tmpPath, { force: true }).catch(() => {});
        throw error;
      }
    },
    async delete(path: string): Promise<void> {
      await fs.rm(resolveSafe(path), { force: true, recursive: true });
    },
    async exists(path: string): Promise<boolean> {
      try {
        await fs.access(resolveSafe(path));
        return true;
      } catch {
        return false;
      }
    },
    async list(path: string): Promise<string[]> {
      try {
        return await fs.readdir(resolveSafe(path));
      } catch {
        return [];
      }
    },
  };
}
