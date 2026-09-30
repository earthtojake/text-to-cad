import { useEffect, useRef, useSyncExternalStore } from "react";
import type { LiveRegistry } from "../host/liveRegistry.js";

const THUMBNAIL_WIDTH = 360;

/** A PNG of the view, scaled to at most `width` pixels wide. */
export async function scaledPng(image: Blob, width: number): Promise<Blob> {
  const bitmap = await createImageBitmap(image);
  try {
    const scale = Math.min(1, width / bitmap.width);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("Could not encode the thumbnail.")), "image/png"));
  } finally { bitmap.close(); }
}

/**
 * Keep a small picture of each model a view shows, for the library: once the model has drawn,
 * `save` is handed a PNG of it. Once per model per mounted view; a failure is left alone, since a
 * thumbnail is a nicety.
 */
export function useModelThumbnail(live: LiveRegistry, model: string | null, save: (png: Blob, model: string) => Promise<unknown>) {
  const taken = useRef(new Set<string>());
  const latest = useRef(save);
  latest.current = save;
  const controller = useSyncExternalStore(live.subscribe, live.current, live.current);
  useEffect(() => {
    if (!controller || !model || taken.current.has(model)) return;
    let cancelled = false;
    const attempt = async (tries: number) => {
      if (cancelled) return;
      const state = controller.readState();
      if (state.loading || state.active === false) {
        if (tries > 0) setTimeout(() => void attempt(tries - 1), 750);
        return;
      }
      taken.current.add(model);
      try {
        const png = await scaledPng(await controller.capture(), THUMBNAIL_WIDTH);
        if (!cancelled) await latest.current(png, model);
      } catch { /* a thumbnail is a nicety */ }
    };
    const timer = setTimeout(() => void attempt(40), 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [controller, model]);
}
