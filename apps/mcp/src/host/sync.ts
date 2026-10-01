import type { CadEditingPreview } from '@text-to-cad/core/client';
import type { Launch, Root, Server, ViewEvent } from './server';
import { encodeBase64 } from './tunnel';

/** How often a view syncs with nothing happening (the server's `views.POLL_SECONDS`). */
export const SYNC_MS = 1_000;
/** How soon it syncs again while a build it watches is moving: its progress, at a readable pace. */
export const NEWS_MS = 150;

export interface ViewSyncHandlers {
  /** The agent asked this view to show a model. */
  show(launch: Launch): void;
  /** A PNG of exactly what the view shows now. */
  capture(): Promise<Blob>;
  /** What the view shows and has selected, for the agent (`cad_view`): sent whenever it changes. */
  state(): Record<string, unknown>;
}

/** What the mounted model view watches, through its client: its root's catalog. */
export interface ViewSyncWatch {
  root: Pick<Root, 'kind' | 'path'>;
  /** The file on screen, as the root names it; null on the home. */
  file(): string | null;
  /** The server's revision of the catalog the client last applied ('' before one). */
  revision(): string;
  /** Read the catalog again: the server says it moved. */
  refresh(file: string | null): Promise<unknown>;
}

type PreviewListener = { onUpdate(preview: CadEditingPreview): void; onError(error: unknown): void };

export interface ViewSync {
  /** Attach the model view's watch; the returned function detaches it. */
  watch(watch: ViewSyncWatch): () => void;
  /** A file's build feed, heard on the sync: the client's `editingPreviewFeed`. */
  observePreview(file: string, onUpdate: (preview: CadEditingPreview) => void, onError: (error: unknown) => void): () => void;
  /** A person touched this view, or it shows something new: it is the one the agent's tools mean. Syncs now. */
  focus(): void;
  /** A newer view took this one's place: one last sync says so, and the loop ends. */
  close(): Promise<void>;
  /** Sync until `signal` aborts. */
  run(signal: AbortSignal): void;
}

/**
 * A view's ONE call to the server, each second (`cad_sync`). Up go what it shows (its model; its
 * state whenever that changed, which is what the agent reads; that a person just touched it) and
 * what it watches (its root's catalog, any STEP's build feed). Back come the agent's requests for
 * it, the catalog's revision — the view reads the catalog again only when it moves — and each
 * feed's status. Nothing is held open: a host relays every call through a few slots all its views
 * share, and a held one would keep the others' model loads waiting. A sync that brought news (an
 * event, a moving build) is followed by the next sooner.
 */
export function createViewSync(server: Pick<Server, 'sync' | 'reply'>,
  view: { id: string; surface: string; model(): string | null; hidden?(): boolean }, handlers: ViewSyncHandlers): ViewSync {
  let watched: ViewSyncWatch | null = null;
  // The catalog revision a refresh was started for, so one change reads the catalog once.
  let requested = '';
  const previews = new Map<string, { listeners: Set<PreviewListener>; cursor: string | null }>();
  let focused = false;
  let sentState = '';
  let closed = false;
  let wake: (() => void) | null = null;
  const wakeNow = () => { const resolve = wake; wake = null; resolve?.(); };
  const pause = (ms: number, signal: AbortSignal) => new Promise<void>(resolve => {
    function done() { clearTimeout(timer); signal.removeEventListener('abort', done); if (wake === done) wake = null; resolve(); }
    const timer = setTimeout(done, ms);
    signal.addEventListener('abort', done, { once: true });
    wake = done;
  });

  async function answer(event: ViewEvent) {
    if (event.type === 'show') { handlers.show(event.launch); return; }
    try {
      const png = await handlers.capture();
      await server.reply(event.requestId, { png: encodeBase64(new Uint8Array(await png.arrayBuffer())) });
    } catch (error) {
      await server.reply(event.requestId, { error: error instanceof Error ? error.message : String(error) }).catch(() => {});
    }
  }

  function changedState(): Record<string, unknown> | undefined {
    try {
      const state = handlers.state();
      return JSON.stringify(state) === sentState ? undefined : state;
    } catch { return undefined; }
  }

  return {
    watch(next) {
      watched = next;
      requested = '';
      wakeNow();
      return () => { if (watched === next) watched = null; };
    },
    observePreview(file, onUpdate, onError) {
      let slot = previews.get(file);
      if (!slot) { slot = { listeners: new Set(), cursor: null }; previews.set(file, slot); }
      const listener = { onUpdate, onError };
      const owned = slot;
      owned.listeners.add(listener);
      wakeNow();
      return () => {
        owned.listeners.delete(listener);
        if (!owned.listeners.size && previews.get(file) === owned) previews.delete(file);
      };
    },
    focus() { focused = true; wakeNow(); },
    async close() {
      closed = true;
      wakeNow();
      await server.sync({ view: view.id, surface: view.surface, model: view.model(), closed: true }).catch(() => {});
    },
    run(signal) {
      void (async () => {
        let failures = 0;
        while (!signal.aborted && !closed) {
          // A page no one can see watches nothing (the server scans no catalog for it) and still
          // hears the agent; shown again, its next sync catches up on what moved.
          const watch = view.hidden?.() ? null : watched;
          const files = watch ? [...previews.keys()] : [];
          const state = changedState();
          const touched = focused;
          focused = false;
          try {
            const reply = await server.sync({
              view: view.id, surface: view.surface, model: view.model(),
              ...(touched ? { focused: true } : {}),
              ...(state ? { state } : {}),
              ...(watch ? { watch: { root: { kind: watch.root.kind, path: watch.root.path }, file: watch.file(), ...(files.length ? { previews: files } : {}) } } : {}),
            }, { signal });
            failures = 0;
            if (state) sentState = JSON.stringify(state);
            for (const event of reply.events) void answer(event);
            const revision = reply.catalog?.revision;
            if (watch && watched === watch && revision && revision !== watch.revision() && revision !== requested) {
              requested = revision;
              void watch.refresh(watch.file()).catch(() => { if (requested === revision) requested = ''; });
            }
            let news = false;
            for (const preview of reply.previews ?? []) {
              const slot = previews.get(preview.file);
              if (!slot) continue;
              if (preview.error) { for (const listener of slot.listeners) listener.onError(new Error(preview.error)); continue; }
              const cursor = typeof preview.feedCursor === 'string' ? preview.feedCursor : null;
              if (cursor !== slot.cursor) news = true;
              slot.cursor = cursor;
              for (const listener of slot.listeners) listener.onUpdate(preview);
            }
            // Events may have more behind them: ask again at once. A moving build, soon. Else a second.
            if (!reply.events.length) await pause(news ? NEWS_MS : SYNC_MS, signal);
          } catch {
            if (touched) focused = true;
            if (signal.aborted) return;
            failures += 1;
            await pause(Math.min(30_000, 500 * 2 ** Math.min(failures, 6)), signal);
          }
        }
      })();
    },
  };
}
