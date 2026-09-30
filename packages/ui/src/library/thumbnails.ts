import { useEffect, useRef, useSyncExternalStore } from "react";
import type { LiveRegistry } from "../host/liveRegistry.js";

/**
 * A library card's picture, in pixels: the card's own 4:3, at twice the size a card is drawn at on
 * a wide screen, so it stays sharp on a dense one and small enough for the library to keep.
 */
export const THUMBNAIL_SIZE = Object.freeze({ width: 480, height: 360 });

/**
 * Keep a picture of each model a view shows, for the library: once the view has settled — the
 * whole file loaded and drawn — `save` is handed its picture (`LiveView.thumbnail`: the model
 * framed whole from the default direction at the card's aspect, whatever the person's camera).
 * Once per file per mounted view; a failure is left alone, since a picture is a nicety.
 *
 * `file` is the root-relative path of the file on screen, as the viewer names it: a picture of
 * any other file — the view moved on before it settled — is never saved as this one's.
 */
export function useModelThumbnail(live: LiveRegistry, file: string | null, save: (png: Blob, file: string) => Promise<unknown>) {
  const taken = useRef(new Set<string>());
  const latest = useRef(save);
  latest.current = save;
  const controller = useSyncExternalStore(live.subscribe, live.current, live.current);
  useEffect(() => {
    if (!controller || !file || taken.current.has(file)) return;
    let cancelled = false;
    void controller.thumbnail(THUMBNAIL_SIZE).then(png => {
      const state = controller.readState();
      if (cancelled || state.active === false || state.resource?.kind !== "workspace-file" || state.resource.path !== file) return;
      taken.current.add(file);
      return latest.current(png, file);
    }).catch(() => { /* a picture is a nicety */ });
    return () => { cancelled = true; };
  }, [controller, file]);
}
