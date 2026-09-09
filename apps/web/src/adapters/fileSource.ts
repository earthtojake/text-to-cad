import { copyTextToClipboard } from '@hardcore/ui/clipboard';
import type { FileEntry, FileMetadata, FileSource } from '@hardcore/ui/file-viewer';
import type { createCadClient, CadEntry, CadServerInfo } from '@hardcore/core/client';

export type CadClient = ReturnType<typeof createCadClient>;
export const catalogPath = (entry: CadEntry): string => String(entry.rootRelativeFile || entry.file || '').trim().replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');

/** Catalog access remains read-only; the shared viewer derives menus from these capabilities. */
export function createWebFileSource(client: CadClient, server: CadServerInfo, { onCopyStatus }: { onCopyStatus?: (message: string) => void } = {}): FileSource {
  const paths = () => client.getSnapshot().entries.map(catalogPath).filter(Boolean);
  async function ready(signal: AbortSignal) {
    signal.throwIfAborted();
    if (!client.getSnapshot().hydrated) await client.refresh({ signal });
    signal.throwIfAborted();
  }
  const copy = async (entry: { path: string }, absolute = false) => {
    const catalogEntry = client.getSnapshot().entries.find(candidate => catalogPath(candidate) === entry.path);
    if (!catalogEntry) return;
    const rootPath = String(server.rootPath || '').replace(/[\\/]+$/, '');
    const rawPath = String(catalogEntry.file).trim().replace(/\\/g, '/');
    const rootPrefix = rootPath.replace(/\\/g, '/');
    const relativePath = rawPath.startsWith(`${rootPrefix}/`) ? rawPath.slice(rootPrefix.length + 1) : catalogPath(catalogEntry);
    const text = absolute ? `${rootPath}${rootPath.includes('\\') ? '\\' : '/'}${rootPath.includes('\\') ? relativePath.replace(/\//g, '\\') : relativePath}` : relativePath;
    onCopyStatus?.('');
    await copyTextToClipboard(text);
    const filename = relativePath.split('/').pop() || '';
    const label = absolute ? 'Copied path' : 'Copied relative path';
    onCopyStatus?.(filename && text !== filename ? `${label} for ${filename}` : label);
  };
  return {
    id: server.rootId,
    rootName: 'This directory',
    async stat(path, { signal }): Promise<FileMetadata> {
      const entry = await client.resolveEntry(path, { signal });
      signal.throwIfAborted();
      const relative = catalogPath(entry);
      return { path: relative, name: relative.split('/').pop() || relative, kind: 'file', size: Number(entry.bytes || 0), extension: relative.split('.').pop()?.toLowerCase() || '', mediaType: 'cad' };
    },
    async list(directory, { signal }) {
      await ready(signal);
      const prefix = directory ? `${directory}/` : '';
      const entries = new Map<string, FileEntry>();
      for (const path of paths()) {
        if (!path.startsWith(prefix)) continue;
        const rest = path.slice(prefix.length);
        if (!rest) continue;
        const name = rest.split('/')[0];
        const child = prefix + name;
        entries.set(child, { path: child, name, kind: rest.includes('/') ? 'directory' : 'file' });
      }
      return [...entries.values()].sort((a, b) => Number(b.kind === 'directory') - Number(a.kind === 'directory') || a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
    },
    async paths({ signal }) { await ready(signal); return paths(); },
    subscribe(listener) {
      let previous = client.getSnapshot().entries;
      return client.subscribe(() => {
        const current = client.getSnapshot().entries;
        if (current === previous) return;
        const before = new Map(previous.map(entry => [catalogPath(entry), JSON.stringify(entry)]));
        const after = new Map(current.map(entry => [catalogPath(entry), JSON.stringify(entry)]));
        const changed = [...new Set([...before.keys(), ...after.keys()])].filter(path => before.get(path) !== after.get(path));
        previous = current;
        if (changed.length) listener({ sourceId: server.rootId, paths: changed });
      });
    },
    actions: {
      platform: navigator.userAgent.includes('Macintosh') ? 'darwin' : navigator.userAgent.includes('Windows') ? 'win32' : 'linux',
      perform: {
        'copy-relative-path': entry => copy(entry),
        'copy-reference': entry => copy(entry),
        ...((server.backend || 'local-fs') === 'local-fs' && server.rootPath ? { 'copy-path': (entry: { path: string }) => copy(entry, true) } : {}),
      },
    },
  };
}
