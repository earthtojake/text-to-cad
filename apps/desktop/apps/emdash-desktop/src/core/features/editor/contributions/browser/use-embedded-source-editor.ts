import type { HostFileRef } from '@emdash/core/primitives/path/api';
import type * as monacoNS from 'monaco-editor';
import { useCallback, useEffect, useRef, useState } from 'react';
import { encodeFacetUri } from '@core/features/editor/api/browser/facet-binder/facet-uri';
import {
  openFileStore,
  type OpenFileEntry,
  type SaveFileError,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import { installMonacoFacetBinder } from '@core/features/editor/browser/monaco/install-monaco-facet-binder';
import { monacoBootstrap } from '@core/features/editor/browser/monaco/monaco-bootstrap';
import {
  addMonacoKeyboardShortcuts,
  configureMonacoEditor,
} from '@core/features/editor/browser/monaco/monaco-config';
import { DEFAULT_EDITOR_OPTIONS } from '@core/features/editor/browser/renderers/utils';

const BUFFER = { kind: 'buffer' } as const;

export type EmbeddedSourceEditorSaveResult =
  | { success: true }
  | { success: false; error: SaveFileError };

export function useEmbeddedSourceEditor(input: {
  fileRef: HostFileRef;
  effectiveTheme: string;
  onSavedByKeyboard: () => void;
  readOnly?: boolean;
}) {
  const [entry, setEntry] = useState<OpenFileEntry | null>(null);
  const [editor, setEditor] = useState<monacoNS.editor.IStandaloneCodeEditor | null>(null);
  const editorHostRef = useRef<HTMLDivElement>(null);
  const keyboardSaveRef = useRef(input.onSavedByKeyboard);
  keyboardSaveRef.current = input.onSavedByKeyboard;

  useEffect(() => {
    installMonacoFacetBinder();
    const lease = openFileStore.acquire(input.fileRef, BUFFER);
    setEntry(lease.entry);
    return () => lease.release();
  }, [input.fileRef]);

  useEffect(() => {
    monacoBootstrap.setTheme(input.effectiveTheme);
  }, [input.effectiveTheme]);

  useEffect(() => {
    let disposed = false;
    let createdEditor: monacoNS.editor.IStandaloneCodeEditor | null = null;
    const facetUri = encodeFacetUri(input.fileRef, BUFFER);
    void monacoBootstrap.init().then((monaco) => {
      if (disposed || !editorHostRef.current) return;
      createdEditor = monaco.editor.create(editorHostRef.current, {
        ...DEFAULT_EDITOR_OPTIONS,
        glyphMargin: true,
        readOnly: input.readOnly,
      });
      configureMonacoEditor(createdEditor);
      addMonacoKeyboardShortcuts(createdEditor, monaco, {
        onSave: () => {
          if (!input.readOnly) keyboardSaveRef.current();
        },
      });
      setEditor(createdEditor);
    });
    return () => {
      disposed = true;
      if (!createdEditor) return;
      installMonacoFacetBinder().detach(createdEditor, facetUri);
      createdEditor.dispose();
    };
  }, [input.fileRef, input.readOnly]);

  useEffect(() => {
    editor?.updateOptions({ readOnly: input.readOnly });
  }, [editor, input.readOnly]);

  const bufferHandle = entry?.handleFor(BUFFER);
  useEffect(() => {
    if (!editor || !bufferHandle) return;
    const uri = encodeFacetUri(input.fileRef, BUFFER);
    const binder = installMonacoFacetBinder();
    binder.attach(editor, uri);
    editor.focus();
    return () => binder.detach(editor, uri);
  }, [bufferHandle, editor, input.fileRef]);

  const save = useCallback(async (): Promise<EmbeddedSourceEditorSaveResult> => {
    if (!entry) return { success: false, error: { type: 'not-open' } };
    return await openFileStore.save(entry);
  }, [entry]);

  const discard = useCallback(() => {
    if (entry) openFileStore.reloadFromDisk(entry);
  }, [entry]);

  return {
    entry,
    editorHostRef,
    save,
    discard,
    loading: !entry || entry.status.kind === 'loading' || !bufferHandle,
  };
}
