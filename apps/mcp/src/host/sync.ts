import { encodeBase64 } from '@text-to-cad/core/client';
import type { Launch, Server, ViewEvent } from './server';

/** How often a view syncs with nothing happening (the server's `views.POLL_SECONDS`). */
export const SYNC_MS = 1_000;
// Syncs failing in a row before a view says its server is gone (about seven seconds, with the backoff).
export const LOST_AFTER = 4;

export interface ViewSyncHandlers {
  /** The agent asked this view to show a model. */
  show(launch: Launch): void;
  /** A PNG of exactly what the view shows now. */
  capture(): Promise<Blob>;
  /** What the view shows and has selected, for the agent (`cad_view`): sent whenever it changes. */
  state(): Record<string, unknown>;
  /**
   * Whether the server still answers: false once `LOST_AFTER` syncs in a row have failed (its process
   * has gone, and the host does not start it again on its own), true when one succeeds again.
   */
  connection?(connected: boolean): void;
}

/** What the mounted model view watches, through its client: its file's catalog entry. */
export interface ViewSyncWatch {
  /** The file on screen, by its absolute path; null on the home, which watches nothing. */
  file(): string | null;
  /** The server's revision of the catalog the client last applied ('' before one). */
  revision(): string;
  /** Read the catalog again: the server says it moved. */
  refresh(file: string | null): Promise<unknown>;
}

export interface ViewSync {
  /** Attach the model view's watch; the returned function detaches it. */
  watch(watch: ViewSyncWatch): () => void;
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
 * what it watches (its file's catalog entry). Back come the agent's requests for it and the
 * catalog's revision — the view reads the catalog again only when it moves. Nothing is held open:
 * a host relays every call through a few slots all its views share, and a held one would keep the
 * others' model loads waiting. A sync that brought events is followed by the next at once.
 */
export function createViewSync(server: Pick<Server, 'sync' | 'reply'>,
  view: { id: string; surface: string; model(): string | null }, handlers: ViewSyncHandlers): ViewSync {
  let watched: ViewSyncWatch | null = null;
  // The catalog revision a refresh was started for, so one change reads the catalog once.
  let requested = '';
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
          // Every view watches, seen or not: a tab in the background is current when it is shown.
          const watch = watched;
          const watchedFile = watch?.file() ?? null;
          const state = changedState();
          const touched = focused;
          focused = false;
          try {
            const reply = await server.sync({
              view: view.id, surface: view.surface, model: view.model(),
              ...(touched ? { focused: true } : {}),
              ...(state ? { state } : {}),
              ...(watchedFile ? { watch: { file: watchedFile } } : {}),
            }, { signal });
            if (failures >= LOST_AFTER) handlers.connection?.(true);
            failures = 0;
            if (state) sentState = JSON.stringify(state);
            for (const event of reply.events) void answer(event);
            const revision = reply.catalog?.revision;
            if (watch && watched === watch && revision && revision !== watch.revision() && revision !== requested) {
              requested = revision;
              void watch.refresh(watch.file()).catch(() => { if (requested === revision) requested = ''; });
            }
            // Events may have more behind them: ask again at once. Else a second.
            if (!reply.events.length) await pause(SYNC_MS, signal);
          } catch {
            if (touched) focused = true;
            if (signal.aborted) return;
            failures += 1;
            if (failures === LOST_AFTER) handlers.connection?.(false);
            await pause(Math.min(30_000, 500 * 2 ** Math.min(failures, 6)), signal);
          }
        }
      })();
    },
  };
}
