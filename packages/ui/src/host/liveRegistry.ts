/** The size a picture for a library card is drawn at, in pixels. */
export interface ThumbnailSize { width: number; height: number }

/** What a mounted renderer's live controller answers, whichever family it is. */
export interface LiveView {
  readState(): { loading?: boolean; active?: boolean; resource?: { kind: string; path?: string } };
  /** What the view shows right now, as it shows it. */
  capture(): Promise<Blob>;
  /**
   * The model on its own, for a library card: once the view has settled — the whole file loaded
   * and drawn — framed whole from the default direction at `size`, whatever the person's camera,
   * panels or window. Nothing on screen changes. A view that draws the file in the dark theme's own
   * colours too (a KiCad board's) hands its light picture carrying the dark one as `dark`, which the
   * library keeps beside it (`CadClient.keepThumbnail`) and shows in the dark theme.
   */
  thumbnail(size: ThumbnailSize): Promise<Blob & { dark?: Blob }>;
}

/** The mounted view's live controller, bound by whichever renderer is showing. */
export interface LiveRegistry<Controller extends LiveView = LiveView> {
  /** A renderer's `live`: the renderer binds its controller here while it is mounted. */
  binding: { bind(controller: Controller): () => void };
  current(): Controller | null;
  subscribe(listener: () => void): () => void;
}

/** A host's handle on the view it shows: pass `binding` to the renderers, read the view through `current()`. */
export function createLiveRegistry<Controller extends LiveView = LiveView>(): LiveRegistry<Controller> {
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
