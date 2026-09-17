import { useLayoutEffect, useRef } from 'react';
import type { RefObject } from 'react';
import type { DocumentSession, FileSource } from '../file-viewer/types.js';
import type { ViewerCommandTarget, ViewerHost } from './types.js';

/** The app owns registration/dispatch; this view owns operation and generation guards. */
export function useViewerCommands({ host, generation, path, document, reload, element }: {
  host: ViewerHost; generation: string; path: string | null; document: DocumentSession | null;
  reload(): void; element: RefObject<HTMLDivElement | null>;
}) {
  const current = useRef({ generation, source: host.files, document, reload });
  current.current = { generation, source: host.files, document, reload };
  const source: FileSource = host.files;
  useLayoutEffect(() => {
    if (!host.commands) return;
    let bound = true;
    const valid = () => bound && current.current.generation === generation && current.current.source === source;
    const target: ViewerCommandTarget = {
      sourceId: source.id, path, generation,
      async save() {
        if (!valid()) return { status: 'stale' };
        const document = current.current.document;
        if (!document || document.readOnly) return { status: 'unavailable' };
        try {
          const result = await document.save();
          if (!valid()) return { status: 'stale', committed: result.status === 'saved' || (result.status === 'stale' && result.committed) };
          if (result.status === 'saved') return { status: 'completed' };
          if (result.status === 'error') return { status: 'failed', message: result.message };
          return result;
        } catch (error) {
          return valid() ? { status: 'failed', message: error instanceof Error ? error.message : String(error) } : { status: 'stale' };
        }
      },
      reload() {
        if (!valid()) return { status: 'stale' };
        if (!path) return { status: 'unavailable' };
        // The reload invalidates this target immediately, even before React
        // publishes the replacement document generation.
        bound = false;
        current.current.reload();
        return { status: 'completed' };
      },
      focus() {
        if (!valid()) return { status: 'stale' };
        if (!element.current?.isConnected) return { status: 'unavailable' };
        element.current.focus({ preventScroll: true });
        return { status: 'completed' };
      },
    };
    const unbind = host.commands.bind(target);
    return () => { bound = false; unbind(); };
  }, [host.commands, source, generation, path, element]);
}
