import { isMissingFileError } from "@text-to-cad/core/client";
import { useCallback, useEffect, useRef, useState } from "react";
import { selectRenderer } from "../registry.js";
import type { FileMetadata, FileSource, PreparedRenderer, RendererRegistration } from "../types.js";

type ReadyDocument = { status: "ready"; file: FileMetadata; renderer: RendererRegistration; prepared: PreparedRenderer };
export type LoadedDocument = ReadyDocument | { status: "empty" } | { status: "loading" } | { status: "error"; message: string; missing: boolean };

export function errorMessage(error: unknown): string { return error instanceof Error ? error.message : String(error); }

/** The lifetime of one file, by its absolute path. Source identity participates in every asynchronous guard. */
export function useFileDocument(path: string | null, source: FileSource, renderers: readonly RendererRegistration[]) {
  const [generation, setGeneration] = useState(0);
  const key = JSON.stringify([source.id, path, generation]);
  const [result, setResult] = useState<{ key: string; document: LoadedDocument } | null>(null);
  const loaded: LoadedDocument = result?.key === key ? result.document : { status: path === null ? "empty" : "loading" };
  // A live document follows its file itself (`PreparedDocument.live`): its content changes are not ours.
  const live = loaded.status === "ready" && loaded.prepared.live === true;
  const current = useRef({ key, source, live });
  current.current = { key, source, live };
  const reload = useCallback(() => setGeneration((value) => value + 1), []);
  const previousLoad = useRef<{ key: string; source: FileSource; path: string | null; generation: number; refresh: boolean } | null>(null);

  useEffect(() => {
    const previous = previousLoad.current;
    const refresh = previous?.key === key && previous.source === source ? previous.refresh
      : previous?.source === source && previous.path === path && previous.generation !== generation;
    previousLoad.current = { key, source, path, generation, refresh };
    if (path === null) return;
    const controller = new AbortController();
    const { signal } = controller;
    let owned: PreparedRenderer | undefined;
    void (async () => {
      try {
        const metadata = await source.stat(path, { signal });
        signal.throwIfAborted();
        const renderer = selectRenderer(renderers, metadata);
        const prepared = await renderer.prepare({ file: metadata, source, signal, refresh });
        if (signal.aborted) { prepared.dispose?.(); return; }
        owned = prepared;
        setResult({ key, document: { status: "ready", file: metadata, renderer, prepared } });
      } catch (error) {
        if (!signal.aborted) setResult({ key, document: { status: "error", message: errorMessage(error), missing: isMissingFileError(error) } });
      }
    })();
    return () => { controller.abort(); owned?.dispose?.(); };
  }, [key, path, source, renderers]);

  useEffect(() => {
    if (!path || !source.subscribe) return;
    return source.subscribe((change) => {
      if (change.sourceId !== source.id) return;
      const state = current.current;
      if (state.key !== key || state.source !== source || state.live) return;
      // A live document is updated in place by its renderer; any other reopens on a new revision.
      if (change.changes.some(item => item.kind === "content" && item.path === path)) reload();
    });
  }, [key, path, source, reload]);

  return { loaded, key, reload, path };
}
