/** What a mounted renderer's live controller answers, whichever family it is. */
export interface LiveCapture {
  readState(): { loading?: boolean; active?: boolean };
  capture(): Promise<Blob>;
}

/** The mounted view's live controller, bound by whichever renderer is showing. */
export interface LiveRegistry<Controller extends LiveCapture = LiveCapture> {
  /** A renderer's `live`: the renderer binds its controller here while it is mounted. */
  binding: { bind(controller: Controller): () => void };
  current(): Controller | null;
  subscribe(listener: () => void): () => void;
}

/** A host's handle on the view it shows: pass `binding` to the renderers, read the view through `current()`. */
export function createLiveRegistry<Controller extends LiveCapture = LiveCapture>(): LiveRegistry<Controller> {
  let current: Controller | null = null;
  const listeners = new Set<() => void>();
  const changed = () => { for (const listener of [...listeners]) listener(); };
  return {
    binding: {
      bind(controller) {
        current = controller;
        changed();
        return () => { if (current === controller) { current = null; changed(); } };
      },
    },
    current: () => current,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  };
}
