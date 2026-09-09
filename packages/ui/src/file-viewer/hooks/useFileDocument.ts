import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { selectRenderer } from "../registry.js";
import type { DocumentSession, FileMetadata, FileSource, PreparedRenderer, RendererRegistration, TextDocument } from "../types.js";

type ReadyDocument = { status: "ready"; file: FileMetadata; renderer: RendererRegistration; prepared: PreparedRenderer };
export type LoadedDocument = ReadyDocument | { status: "empty" } | { status: "loading" } | { status: "error"; message: string };
type EditState = { key: string; base: TextDocument; value: string; saving: boolean; stale: boolean; error: string | null };

export function errorMessage(error: unknown): string { return error instanceof Error ? error.message : String(error); }

/** The lifetime of one file. Source identity participates in every asynchronous guard. */
export function useFileDocument(file: string | FileMetadata | null, source: FileSource, renderers: readonly RendererRegistration[]) {
  const path = typeof file === "string" ? file : file?.path ?? null;
  const [generation, setGeneration] = useState(0);
  const key = JSON.stringify([source.id, path, generation]);
  const [result, setResult] = useState<{ key: string; document: LoadedDocument } | null>(null);
  const [edit, setEdit] = useState<EditState | null>(null);
  const current = useRef({ key, edit, source });
  current.current = { key, edit, source };
  const writes = useRef(new Set<AbortController>());
  const reload = useCallback(() => setGeneration((value) => value + 1), []);

  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    const { signal } = controller;
    let owned: PreparedRenderer | undefined;
    void (async () => {
      try {
        const metadata = typeof file === "object" && file !== null ? file : await source.stat(path, { signal });
        signal.throwIfAborted();
        const renderer = selectRenderer(renderers, metadata);
        const prepared = await renderer.prepare({ file: metadata, source, signal });
        if (signal.aborted) { prepared.dispose?.(); return; }
        owned = prepared;
        setResult({ key, document: { status: "ready", file: metadata, renderer, prepared } });
        if (prepared.text) setEdit({ key, base: prepared.text, value: prepared.text.content, saving: false, stale: false, error: null });
      } catch (error) {
        if (!signal.aborted) setResult({ key, document: { status: "error", message: errorMessage(error) } });
      }
    })();
    return () => { controller.abort(); owned?.dispose?.(); };
    // Metadata is refreshed on explicit reload; its object identity is not a file change.
  }, [key, path, source, renderers]);

  useEffect(() => () => {
    for (const controller of writes.current) controller.abort();
    writes.current.clear();
  }, [key, source]);

  useEffect(() => {
    if (!path || !source.subscribe) return;
    return source.subscribe((change) => {
      if (change.sourceId !== source.id || !change.paths.includes(path)) return;
      const state = current.current;
      if (state.key !== key || state.source !== source) return;
      const document = state.edit?.key === key ? state.edit : null;
      if (document && document.value !== document.base.content) {
        setEdit((previous) => previous?.key === key ? { ...previous, stale: true } : previous);
      } else reload();
    });
  }, [key, path, source, reload]);

  const setValue = useCallback((value: string) => {
    setEdit((previous) => previous?.key === key && !previous.base.readOnly && !previous.base.truncated && source.writeText
      ? { ...previous, value, error: null } : previous);
  }, [key, source]);
  const keepMine = useCallback(() => setEdit((previous) => previous?.key === key ? { ...previous, stale: false } : previous), [key]);
  const save = useCallback(async () => {
    const state = current.current;
    const document = state.edit;
    if (!path || state.key !== key || state.source !== source || document?.key !== key || document.saving || [...writes.current].some((write) => !write.signal.aborted)
      || document.base.readOnly || document.base.truncated || !source.writeText) return;
    const controller = new AbortController();
    writes.current.add(controller);
    setEdit((previous) => previous?.key === key ? { ...previous, saving: true, error: null } : previous);
    try {
      const written = await source.writeText(path, { content: document.value, expectedRevision: document.base.revision, signal: controller.signal });
      if (controller.signal.aborted || current.current.key !== key || current.current.source !== source) return;
      setEdit((previous) => {
        if (previous?.key !== key) return previous;
        if (written.status === "saved") return {
          ...previous,
          base: written.document,
          // Typing during the write must survive its eventual response.
          value: previous.value === document.value ? written.document.content : previous.value,
          stale: false,
          saving: false,
          error: null,
        };
        return { ...previous, saving: false, stale: written.status === "conflict" || previous.stale,
          error: written.status === "error" ? written.message : null };
      });
    } catch (error) {
      if (!controller.signal.aborted && current.current.key === key && current.current.source === source) {
        setEdit((previous) => previous?.key === key ? { ...previous, saving: false, error: errorMessage(error) } : previous);
      }
    } finally { writes.current.delete(controller); }
  }, [key, path, source]);

  const loaded: LoadedDocument = result?.key === key ? result.document : { status: path === null ? "empty" : "loading" };
  const document = useMemo<DocumentSession | null>(() => edit?.key === key && loaded.status === "ready" && loaded.prepared.text ? {
    key, value: edit.value, revision: edit.base.revision, readOnly: !!edit.base.readOnly || !!edit.base.truncated || !source.writeText,
    dirty: edit.value !== edit.base.content, saving: edit.saving, stale: edit.stale, error: edit.error,
    setValue, save, reload, keepMine,
  } : null, [edit, key, loaded, source, setValue, save, reload, keepMine]);
  return { loaded, document, key, reload, path };
}
