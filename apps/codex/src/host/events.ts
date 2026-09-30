import type { Launch, Server, ViewEvent } from './server';
import { encodeBase64 } from './tunnel';

export interface ViewEventHandlers {
  /** The agent asked this view to show a model. */
  show(launch: Launch): void;
  /** A PNG of exactly what the view shows now. */
  capture(): Promise<Blob>;
  /** What the view shows and has selected, for the agent. */
  describe(): Record<string, unknown>;
}

const pause = (ms: number, signal: AbortSignal) => new Promise<void>(resolve => {
  const timer = setTimeout(done, ms);
  function done() { clearTimeout(timer); signal.removeEventListener('abort', done); resolve(); }
  signal.addEventListener('abort', done, { once: true });
});

/**
 * Keep one `cad_events` long-poll outstanding for this view until `signal` aborts. Each poll
 * also registers the view, so a server that restarted learns it again on the next one.
 */
export function watchViewEvents(server: Pick<Server, 'events' | 'reply'>, view: { id: string; surface: string; model(): string | null }, handlers: ViewEventHandlers, signal: AbortSignal): void {
  async function answer(event: ViewEvent) {
    if (event.type === 'show') { handlers.show(event.launch); return; }
    try {
      if (event.type === 'capture') {
        const png = await handlers.capture();
        await server.reply(event.requestId, { png: encodeBase64(new Uint8Array(await png.arrayBuffer())) });
      } else {
        await server.reply(event.requestId, { state: handlers.describe() });
      }
    } catch (error) {
      await server.reply(event.requestId, { error: error instanceof Error ? error.message : String(error) }).catch(() => {});
    }
  }
  void (async () => {
    let failures = 0;
    while (!signal.aborted) {
      try {
        const events = await server.events(view.id, view.surface, view.model(), { signal });
        failures = 0;
        for (const event of events) void answer(event);
      } catch {
        if (signal.aborted) return;
        failures += 1;
        await pause(Math.min(30_000, 500 * 2 ** Math.min(failures, 6)), signal);
      }
    }
  })();
}
