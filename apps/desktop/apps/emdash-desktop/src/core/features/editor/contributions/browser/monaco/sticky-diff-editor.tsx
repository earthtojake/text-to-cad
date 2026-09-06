import { autorun, observable, runInAction } from 'mobx';
import type * as monaco from 'monaco-editor';
import { useEffect, useRef } from 'react';
import type { Facet } from '@core/features/editor/api/browser/open-file-store/facet-handle';
import {
  openFileStore,
  type OpenFileEntry,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import { DIFF_EDITOR_BASE_OPTIONS } from '@core/features/editor/browser/monaco/editorConfig';
import { installMonacoFacetBinder } from '@core/features/editor/browser/monaco/install-monaco-facet-binder';
import { monacoBootstrap } from '@core/features/editor/browser/monaco/monaco-bootstrap';
import { openModal } from '@core/manifests/browser/modal-api';
import { useTheme } from '@core/primitives/theme/browser';

/**
 * One side of a diff, expressed against the OpenFileStore (spec §6): a facet
 * of the file's entry — a git snapshot at some ref, or the editable working
 * buffer — plus the codec facet URI the binder keys its Monaco model and
 * view state by. `empty` renders a blank half (e.g. the modified side of a
 * deleted file before the leases resolve to anything).
 */
export type DiffSideModel =
  | { kind: 'empty' }
  | { kind: 'facet'; entry: OpenFileEntry; facet: Facet; uri: string };

export interface StickyDiffEditorProps {
  /** The old/original (left) side; null while leases are being acquired. */
  original: DiffSideModel | null;
  /** The new/modified (right) side; editable when it is a buffer facet. */
  modified: DiffSideModel | null;
  /** Checkout-relative path, used by the save-conflict dialog. */
  filePath: string;
  diffStyle: 'unified' | 'split';
  /** Called whenever the content height changes, for auto-sizing parent containers. */
  onHeightChange?: (height: number) => void;
  /** Called when the diff editor instance is created/disposed. */
  onEditorChange?: (editor: monaco.editor.IStandaloneDiffEditor | null) => void;
}

const EMPTY_SIDE_URI = 'emdash-diff-empty';

function sideUri(side: DiffSideModel): string {
  return side.kind === 'facet' ? side.uri : EMPTY_SIDE_URI;
}

type ResolvedSide =
  | { type: 'pending' }
  | { type: 'empty' }
  | { type: 'model'; model: monaco.editor.ITextModel };

/**
 * Resolves a side to its Monaco model by observing the entry's status and
 * facet handles (both MobX-observable — callers run this inside a reaction).
 * A git ref that does not contain the path (added files) and a working tree
 * where the file is gone (deleted files, `orphaned`) resolve to the empty
 * half instead of a model; other errors and loading stay pending.
 */
function resolveSide(side: DiffSideModel): ResolvedSide {
  if (side.kind === 'empty') return { type: 'empty' };
  const { entry, facet } = side;
  const status = facet.kind === 'git' ? entry.gitStatus(facet.ref) : entry.status;
  if (!status) return { type: 'pending' };
  if (status.kind === 'ready') {
    const handle = entry.handleFor(facet);
    if (!handle) return { type: 'pending' };
    const model = installMonacoFacetBinder().modelFor(side.uri);
    return model ? { type: 'model', model } : { type: 'pending' };
  }
  if (status.kind === 'orphaned') return { type: 'empty' };
  if (status.kind === 'error' && status.code === 'not-found') return { type: 'empty' };
  return { type: 'pending' };
}

/**
 * Saves the diff's editable buffer through the same store machinery file
 * tabs use: etag-preconditioned write; a conflict runs the shared conflict
 * dialog (accept incoming reloads from disk, keep mine overwrites).
 */
async function saveDiffBuffer(entry: OpenFileEntry, filePath: string): Promise<void> {
  if (!entry.dirty) return;
  const saved = await openFileStore.save(entry);
  if (saved.success || saved.error.type !== 'conflict') return;

  const outcome = await openModal('conflictDialog', { filePath });
  if (!outcome.success) return;
  if (outcome.data) {
    openFileStore.reloadFromDisk(entry);
    return;
  }
  await openFileStore.save(entry, { overwrite: true });
}

export function StickyDiffEditor({
  original,
  modified,
  filePath,
  diffStyle,
  onHeightChange,
  onEditorChange,
}: StickyDiffEditorProps) {
  const mountRef = useRef<HTMLDivElement>(null);

  const modifiedRef = useRef(modified);
  modifiedRef.current = modified;
  const filePathRef = useRef(filePath);
  filePathRef.current = filePath;

  // URI pair of the models currently attached to the editor. The unmount save
  // must key by this, not the side props: the props can already point at a new
  // diff whose models never attached.
  const attachedUrisRef = useRef<{ original: string; modified: string } | null>(null);

  // Blank ITextModels standing in for "nothing at this side" (added/deleted
  // files). Created lazily per component instance, disposed on unmount.
  const emptyModelsRef = useRef<{
    original: monaco.editor.ITextModel | null;
    modified: monaco.editor.ITextModel | null;
  }>({ original: null, modified: null });

  // Observable box so the autorun can react to the editor arriving after async mount.
  const editorBox = useRef(
    observable.box<monaco.editor.IStandaloneDiffEditor | null>(null)
  ).current;

  const onHeightChangeRef = useRef(onHeightChange);
  onHeightChangeRef.current = onHeightChange;

  const onEditorChangeRef = useRef(onEditorChange);
  onEditorChangeRef.current = onEditorChange;

  const { effectiveTheme } = useTheme();

  // Create editor once on mount, dispose on unmount.
  // Monaco is guaranteed ready because monacoBootstrap.init() is awaited in main.tsx.
  useEffect(() => {
    const m = monacoBootstrap.getMonaco();
    if (!m || !mountRef.current) return;

    const editor = m.editor.createDiffEditor(mountRef.current, {
      ...DIFF_EDITOR_BASE_OPTIONS,
      readOnly: true,
      renderSideBySide: diffStyle === 'split',
    });
    onEditorChangeRef.current?.(editor);

    const modifiedEditor = editor.getModifiedEditor();
    modifiedEditor.addCommand(m.KeyMod.CtrlCmd | m.KeyCode.KeyS, () => {
      const side = modifiedRef.current;
      if (side?.kind !== 'facet' || side.facet.kind !== 'buffer') return;
      void saveDiffBuffer(side.entry, filePathRef.current);
    });

    const heightDisposable = modifiedEditor.onDidContentSizeChange(
      (e: { contentHeightChanged: boolean; contentHeight: number }) => {
        if (e.contentHeightChanged) {
          onHeightChangeRef.current?.(e.contentHeight);
        }
      }
    );

    runInAction(() => editorBox.set(editor));

    const emptyModels = emptyModelsRef.current;
    return () => {
      onEditorChangeRef.current?.(null);
      heightDisposable.dispose();
      // Save the viewport before disposal. The sides effect's cleanup can't
      // cover unmount: it runs after this one, when editorBox is already null.
      const attached = attachedUrisRef.current;
      if (attached) {
        installMonacoFacetBinder().saveDiffViewState(attached.original, attached.modified, editor);
      }
      runInAction(() => editorBox.set(null));
      editor.dispose();
      emptyModels.original?.dispose();
      emptyModels.modified?.dispose();
      emptyModels.original = null;
      emptyModels.modified = null;
    };
    // oxlint-disable-next-line react/exhaustive-deps
  }, []);

  // Sync diffStyle changes to the mounted editor.
  useEffect(() => {
    editorBox.get()?.updateOptions({ renderSideBySide: diffStyle === 'split' });
  }, [diffStyle, editorBox]);

  // Sync global Monaco theme (affects all editor instances simultaneously).
  useEffect(() => {
    monacoBootstrap.setTheme(effectiveTheme);
  }, [effectiveTheme]);

  const originalKey = original ? sideUri(original) : null;
  const modifiedKey = modified ? sideUri(modified) : null;

  // Reactive content application — recreated when the sides change.
  // The autorun waits for both sides' store facets to be ready (or resolve to
  // the empty half), then calls setModel in-place without remounting.
  useEffect(() => {
    // Clear the previously-attached models synchronously on side change so the
    // editor doesn't keep showing the previous file's content while the new
    // facets are still loading.
    const current = editorBox.get();
    if (current?.getModel()) {
      current.setModel(null);
      attachedUrisRef.current = null;
    }
    if (!original || !modified) return;

    const emptyModel = (slot: 'original' | 'modified'): monaco.editor.ITextModel | null => {
      const m = monacoBootstrap.getMonaco();
      if (!m) return null;
      let model = emptyModelsRef.current[slot];
      if (!model || model.isDisposed()) {
        model = m.editor.createModel('', undefined);
        emptyModelsRef.current[slot] = model;
      }
      return model;
    };

    const disposer = autorun(() => {
      const editor = editorBox.get(); // reactive: waits for editor to exist
      if (!editor) return;

      const origResolved = resolveSide(original); // reactive via entry observables
      const modResolved = resolveSide(modified);
      if (origResolved.type === 'pending' || modResolved.type === 'pending') return;

      const origModel = origResolved.type === 'model' ? origResolved.model : emptyModel('original');
      const modModel = modResolved.type === 'model' ? modResolved.model : emptyModel('modified');
      if (!origModel || !modModel) return;

      const attached = editor.getModel();
      if (attached?.original === origModel && attached?.modified === modModel) return;
      if (attached) editor.setModel(null);

      editor.setModel({ original: origModel, modified: modModel });
      attachedUrisRef.current = { original: sideUri(original), modified: sideUri(modified) };
      // Edits are only meaningful on a live buffer facet; empty stand-ins and
      // git snapshots stay read-only.
      const editable =
        modified.kind === 'facet' &&
        modified.facet.kind === 'buffer' &&
        modResolved.type === 'model';
      editor.updateOptions({ readOnly: !editable });
      editor.layout();
      // Restore scroll/cursor for the incoming side pair.
      installMonacoFacetBinder().restoreDiffViewState(sideUri(original), sideUri(modified), editor);
      onHeightChangeRef.current?.(editor.getModifiedEditor().getContentHeight());
    });

    return () => {
      // On unmount or side change: save the current viewport so it can be restored later.
      const ed = editorBox.get();
      if (ed?.getModel()) {
        installMonacoFacetBinder().saveDiffViewState(sideUri(original), sideUri(modified), ed);
      }
      disposer();
    };
    // editorBox is a stable ref created once; only side-identity changes recreate the autorun.
    // oxlint-disable-next-line react/exhaustive-deps
  }, [originalKey, modifiedKey]);

  return <div ref={mountRef} className="h-full" />;
}
