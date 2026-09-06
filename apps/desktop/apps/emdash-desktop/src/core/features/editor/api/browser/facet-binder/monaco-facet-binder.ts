import { decodeResourceUri } from '@emdash/core/primitives/path/api';
import type * as monaco from 'monaco-editor';
import { getLanguageFromPath } from '@core/features/editor/api/browser/languageUtils';
import type {
  FacetDescriptor,
  FacetHandle,
  FacetHandleBinder,
} from '@core/features/editor/api/browser/open-file-store/facet-handle';
import { log } from '@core/primitives/logging/browser/logger';
import { decodeFacetUri, encodeFacetUri } from './facet-uri';

/**
 * The Monaco-side projection of OpenFileStore (spec §7): implements
 * {@link FacetHandle} over ITextModel, owns model lifecycle keyed by the
 * facet URI codec, and keeps editor attach/detach and view state
 * (cursor/scroll per buffer, diff-editor view states) — all keyed by facet
 * URI, never in the store.
 *
 * The binder is a renderer of store state: all editing policy (dirty, etag,
 * conflict, save) stays in OpenFileStore. Monaco is obtained lazily through
 * the injected loader; if Monaco fails to initialize, `createHandle` rejects
 * and the store degrades that facet to an error placeholder instead of
 * wedging the stack.
 */
export class MonacoFacetBinder implements FacetHandleBinder {
  /** Live models keyed by facet URI string; refs count live handles. */
  private readonly models = new Map<string, { model: monaco.editor.ITextModel; refs: number }>();
  /** Cursor/scroll/folding state per facet URI, saved between attaches. */
  private readonly viewStates = new Map<string, monaco.editor.ICodeEditorViewState>();
  /** Diff-editor view states keyed by `${originalUri}::${modifiedUri}`. */
  private readonly diffViewStates = new Map<string, monaco.editor.IDiffEditorViewState>();

  constructor(private readonly loadMonaco: () => Promise<typeof monaco>) {}

  // ---------------------------------------------------------------------------
  // FacetHandleBinder
  // ---------------------------------------------------------------------------

  async createHandle(descriptor: FacetDescriptor): Promise<FacetHandle> {
    const decoded = decodeResourceUri(descriptor.uri);
    if (!decoded.success) {
      throw new Error(`MonacoFacetBinder: invalid resource URI: ${decoded.error.message}`);
    }
    const uri = encodeFacetUri(decoded.data, descriptor.facet);
    const m = await this.loadMonaco();

    let entry = this.models.get(uri);
    if (entry) {
      // Facet URIs are deterministic per (ResourceUri, facet) and the store
      // holds at most one handle per facet slot, so a second live handle for
      // one URI should be impossible by construction.
      log.warn('MonacoFacetBinder: second live handle for one facet URI', { uri });
      entry.refs += 1;
    } else {
      const monacoUri = m.Uri.parse(uri);
      let model = m.editor.getModel(monacoUri);
      if (model) {
        log.warn('MonacoFacetBinder: adopting unowned Monaco model', { uri });
        if (model.getValue() !== descriptor.initialText) model.setValue(descriptor.initialText);
      } else {
        const fileName = decoded.data.path.segments.at(-1) ?? '';
        model = m.editor.createModel(
          descriptor.initialText,
          getLanguageFromPath(fileName),
          monacoUri
        );
      }
      entry = { model, refs: 1 };
      this.models.set(uri, entry);
    }
    return new MonacoFacetHandle(this, uri, entry.model, descriptor.readonly);
  }

  // ---------------------------------------------------------------------------
  // Model access (ticket 07's editor components)
  // ---------------------------------------------------------------------------

  /** The live ITextModel at a codec-produced facet URI, if any. */
  modelFor(uri: string): monaco.editor.ITextModel | undefined {
    return this.models.get(uri)?.model;
  }

  // ---------------------------------------------------------------------------
  // Editor attach/detach + view state
  // ---------------------------------------------------------------------------

  /**
   * Attaches the model at `uri` to a code editor: saves view state for
   * `previousUri`, sets the model, restores this facet's saved view state,
   * and enforces read-only for non-buffer facets. No-ops when no model is
   * live at `uri`.
   */
  attach(editor: monaco.editor.IStandaloneCodeEditor, uri: string, previousUri?: string): void {
    if (previousUri && previousUri !== uri) this.saveViewState(previousUri, editor);
    const entry = this.models.get(uri);
    if (!entry) return;
    editor.setModel(entry.model);
    const decoded = decodeFacetUri(uri);
    if (decoded.success) {
      editor.updateOptions({ readOnly: decoded.data.facet.kind !== 'buffer' });
    }
    const viewState = this.viewStates.get(uri);
    if (viewState) editor.restoreViewState(viewState);
  }

  /** Saves view state for `previousUri` and releases the editor's model. */
  detach(editor: monaco.editor.IStandaloneCodeEditor, previousUri?: string): void {
    if (previousUri) this.saveViewState(previousUri, editor);
    editor.setModel(null);
  }

  /**
   * Saves the diff editor's viewport state (scroll + cursor) for the model
   * pair. Call before swapping models (i.e. in the effect cleanup).
   */
  saveDiffViewState(
    originalUri: string,
    modifiedUri: string,
    editor: monaco.editor.IStandaloneDiffEditor
  ): void {
    const viewState = editor.saveViewState();
    if (viewState) this.diffViewStates.set(diffKey(originalUri, modifiedUri), viewState);
  }

  /**
   * Restores a previously saved diff-editor viewport state. Call after
   * `editor.setModel()` so the editor has a layout target; no-ops silently
   * if nothing was saved for this pair.
   */
  restoreDiffViewState(
    originalUri: string,
    modifiedUri: string,
    editor: monaco.editor.IStandaloneDiffEditor
  ): void {
    const viewState = this.diffViewStates.get(diffKey(originalUri, modifiedUri));
    if (viewState) editor.restoreViewState(viewState);
  }

  private saveViewState(uri: string, editor: monaco.editor.IStandaloneCodeEditor): void {
    if (!this.models.has(uri)) return;
    const viewState = editor.saveViewState();
    if (viewState) this.viewStates.set(uri, viewState);
  }

  // ---------------------------------------------------------------------------
  // Handle release
  // ---------------------------------------------------------------------------

  /** Called by handles on dispose; the last release disposes the model. */
  releaseHandle(uri: string): void {
    const entry = this.models.get(uri);
    if (!entry) return;
    entry.refs -= 1;
    if (entry.refs > 0) return;
    this.models.delete(uri);
    if (!entry.model.isDisposed()) entry.model.dispose();
    this.viewStates.delete(uri);
    for (const key of [...this.diffViewStates.keys()]) {
      if (key.startsWith(`${uri}::`) || key.endsWith(`::${uri}`)) {
        this.diffViewStates.delete(key);
      }
    }
  }
}

function diffKey(originalUri: string, modifiedUri: string): string {
  return `${originalUri}::${modifiedUri}`;
}

/**
 * FacetHandle over one ITextModel. `setText` applies external content as a
 * minimal ranged edit through `pushEditOperations`, preserving the undo
 * stack and mapping attached-editor cursors/selections through the edit —
 * never `model.setValue`, which would reset both. Change events are
 * delivered synchronously (Monaco fires `onDidChangeContent` inside the
 * edit), which the store's dirty tracking depends on.
 */
class MonacoFacetHandle implements FacetHandle {
  private disposed = false;
  private applyingSetText = false;
  private readonly listeners = new Set<() => void>();
  private readonly contentSubscription: monaco.IDisposable;

  constructor(
    private readonly binder: MonacoFacetBinder,
    private readonly uri: string,
    private readonly model: monaco.editor.ITextModel,
    private readonly readonlyFacet: boolean
  ) {
    this.contentSubscription = model.onDidChangeContent(() => {
      if (this.readonlyFacet && !this.applyingSetText) {
        // Read-only facets accept content only through setText; editors are
        // forced read-only on attach, so this indicates a misrouted edit.
        log.warn('MonacoFacetBinder: content change on a read-only facet', { uri: this.uri });
      }
      for (const listener of [...this.listeners]) listener();
    });
  }

  getText(): string {
    return this.model.getValue();
  }

  setText(text: string): void {
    if (this.disposed || this.model.isDisposed()) return;
    if (this.model.getValue() === text) return;
    this.applyingSetText = true;
    try {
      if (this.readonlyFacet) {
        // No user edits to preserve on read-only mirrors; a full setValue
        // matches the legacy registry's disk/git update path.
        this.model.setValue(text);
        return;
      }
      const edit = minimalEdit(this.model, text);
      if (edit) {
        // Undo-stop boundaries keep the external update in its own undo
        // group instead of merging into the user's last typing group.
        this.model.pushStackElement();
        this.model.pushEditOperations(null, [edit], () => null);
        this.model.pushStackElement();
      }
      if (this.model.getValue() !== text) {
        // EOL normalization inside pushEditOperations can leave the model
        // diverged from the requested text; fall back to a full reset.
        this.model.setValue(text);
      }
    } finally {
      this.applyingSetText = false;
    }
  }

  onDidChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Idempotent; safe during store linger teardown. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.contentSubscription.dispose();
    this.listeners.clear();
    this.binder.releaseHandle(this.uri);
  }
}

/**
 * Single ranged edit turning the model's content into `text`, trimming the
 * common prefix and suffix so cursors and undo entries outside the changed
 * region survive. Returns null when the texts already match.
 */
function minimalEdit(
  model: monaco.editor.ITextModel,
  text: string
): { range: monaco.IRange; text: string } | null {
  const current = model.getValue();
  if (current === text) return null;

  const maxCommon = Math.min(current.length, text.length);
  let prefix = 0;
  while (prefix < maxCommon && current.charCodeAt(prefix) === text.charCodeAt(prefix)) {
    prefix += 1;
  }
  // Never split a surrogate pair at the prefix boundary.
  if (prefix > 0 && isHighSurrogate(current.charCodeAt(prefix - 1))) prefix -= 1;

  let suffix = 0;
  while (
    suffix < maxCommon - prefix &&
    current.charCodeAt(current.length - 1 - suffix) === text.charCodeAt(text.length - 1 - suffix)
  ) {
    suffix += 1;
  }
  if (suffix > 0 && isLowSurrogate(current.charCodeAt(current.length - suffix))) suffix -= 1;

  const start = model.getPositionAt(prefix);
  const end = model.getPositionAt(current.length - suffix);
  return {
    range: {
      startLineNumber: start.lineNumber,
      startColumn: start.column,
      endLineNumber: end.lineNumber,
      endColumn: end.column,
    },
    text: text.slice(prefix, text.length - suffix),
  };
}

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

function isLowSurrogate(code: number): boolean {
  return code >= 0xdc00 && code <= 0xdfff;
}
