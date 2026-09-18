import { emptyDrawingDocument, parseDrawingScene } from '@hardcore/core/drawing';

// Renderer lifetime only. No localStorage, database, file autosave or app-state
// middleware. Lazy readers avoid serializing a large scene on every pointer move.
const drawings = new Map<string, { serialized?: string; read?: () => string }>();
export function getDrawingScene(tabId: string): string | null {
  const entry = drawings.get(tabId);
  return entry ? entry.read?.() ?? entry.serialized ?? JSON.stringify(emptyDrawingDocument()) : null;
}
export function setDrawingScene(tabId: string, serialized: string): void {
  drawings.set(tabId, { serialized: JSON.stringify(parseDrawingScene(serialized)) });
}
export function retainDrawingScene(tabId: string, read: () => string): () => void {
  const entry = { read };
  drawings.set(tabId, entry);
  return () => {
    // Closing disposes the entry first; a late unmount must not resurrect it.
    if (drawings.get(tabId) !== entry) return;
    const serialized = read();
    // A reader may synchronously dispose or replace its tab while snapshotting.
    if (drawings.get(tabId) === entry) drawings.set(tabId, { serialized });
  };
}
export function deleteDrawingScene(tabId: string): void { drawings.delete(tabId); }
