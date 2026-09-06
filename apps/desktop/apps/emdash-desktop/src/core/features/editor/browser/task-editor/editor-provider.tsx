import { autorun } from 'mobx';
import { observer } from 'mobx-react-lite';
import type * as monacoNS from 'monaco-editor';
import { createContext, useCallback, useContext, useEffect, useRef, type ReactNode } from 'react';
import { encodeFacetUri } from '@core/features/editor/api/browser/facet-binder/facet-uri';
import { useIsActiveTask } from '@core/features/tasks/api/browser/hooks/use-is-active-task';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import { useTaskComposition } from '@core/features/workbench/api/browser/task-composition-context';
import { editorScope } from '@core/features/workbench/contributions/scopes';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { useTheme } from '@core/primitives/theme/browser';
import { disabled, enabled, hidden, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { useViewScope, ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';
import { usePaneContext } from '@core/primitives/workbench-shell/browser/tabs/pane-context';
import { installMonacoFacetBinder } from '../monaco/install-monaco-facet-binder';
import { monacoBootstrap } from '../monaco/monaco-bootstrap';
import { addMonacoKeyboardShortcuts, configureMonacoEditor } from '../monaco/monaco-config';
import { registerActiveCodeEditor } from '../renderers/activeCodeEditor';
import { DEFAULT_EDITOR_OPTIONS } from '../renderers/utils';
import {
  activeFilePath as getActiveFilePath,
  activeFileResource as getActiveFileResource,
} from './pane-selectors';

const BUFFER = { kind: 'buffer' } as const;

interface EditorContextValue {
  /**
   * Ref callback that appends the pane's stable Monaco editor container to the
   * given DOM element. Called by MonacoFileRenderer to position the editor host.
   */
  setEditorHost: (el: HTMLElement | null) => void;
}

const EditorContext = createContext<EditorContextValue | null>(null);

export function useEditorContext(): EditorContextValue {
  const ctx = useContext(EditorContext);
  if (!ctx) throw new Error('useEditorContext must be used within EditorProvider');
  return ctx;
}

export const EditorProvider = observer(function EditorProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { projectId, taskId } = useTaskViewContext();
  const taskView = useTaskComposition();
  const { editorView, paneLayout } = taskView;
  const { paneId, pane: paneTabManager } = usePaneContext();
  const { effectiveTheme } = useTheme();
  const isActive = useIsActiveTask(taskId);
  const liveActionDisabledReason = projectAvailabilityUi.getLiveActionDisabledReason(projectId);
  const editorScopeImplementation = {
    'editor.save': () => ({
      availability: () =>
        liveActionDisabledReason
          ? disabled(liveActionDisabledReason)
          : getActiveFilePath(paneTabManager)
            ? enabled
            : hidden,
      execute: () => {
        const path = getActiveFilePath(paneTabManager);
        if (path) void editorView.saveFile(path);
      },
    }),
    'editor.saveAll': () => ({
      availability: () => (liveActionDisabledReason ? disabled(liveActionDisabledReason) : enabled),
      execute: () => {
        void editorView.saveAllFiles();
      },
    }),
  } satisfies ViewScopeImpl<typeof editorScope>;
  const { instance: editorScopeInstance } = useViewScope(
    editorScope({ paneId }),
    editorScopeImplementation
  );

  // Conflict dialog — shown when editorView.pendingConflictPath is set.
  const openConflictModal = useOpenModal('conflictDialog');

  // The directly-created Monaco editor for this pane.
  const editorRef = useRef<monacoNS.editor.IStandaloneCodeEditor | null>(null);
  // The container <div> appended to the pane's host element.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const focusPendingRef = useRef(false);

  // Stable host element provided by PaneContent via setEditorHost.
  const hostRef = useRef<HTMLElement | null>(null);

  // Tracks the previously-attached buffer facet URI so the binder can save
  // view state before switching models.
  const prevBufUriRef = useRef<string | undefined>(undefined);

  // ---------------------------------------------------------------------------
  // Theme sync — update editor theme when app theme changes.
  // When this pane's editor is created it will inherit the current theme.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    monacoBootstrap.setTheme(effectiveTheme);
  }, [effectiveTheme]);

  // ---------------------------------------------------------------------------
  // Editor creation — fires once on mount. Creates a Monaco editor directly
  // using the globally-loaded Monaco instance. Monaco is guaranteed to be loaded
  // before any pane renders (bootstrap awaits init in main.tsx).
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const m = monacoBootstrap.getMonaco();
    if (!m) return;
    const binder = installMonacoFacetBinder();

    const container = document.createElement('div');
    container.style.width = '100%';
    container.style.height = '100%';
    containerRef.current = container;

    const editor = m.editor.create(container, { ...DEFAULT_EDITOR_OPTIONS, glyphMargin: true });
    editorRef.current = editor;

    configureMonacoEditor(editor);

    const cleanupActive = registerActiveCodeEditor(editor);

    addMonacoKeyboardShortcuts(editor, m, {
      onSave: () => {
        const path = getActiveFilePath(paneTabManager);
        if (path) void editorView.saveFile(path);
      },
      onSaveAll: () => {
        void editorView.saveAllFiles();
      },
    });

    const focusDisposable = editor.onDidFocusEditorWidget(() => {
      taskView.setFocusedRegion('main');
      paneLayout.setActiveGroup(paneId);
    });

    if (hostRef.current) {
      hostRef.current.appendChild(container);
      editor.layout();
    }

    return () => {
      focusDisposable.dispose();
      cleanupActive();
      // Save the active file's view state before disposal. Must run here, not in
      // the attachment autorun's cleanup — that fires after the editor is disposed.
      binder.detach(editor, prevBufUriRef.current);
      editor.dispose();
      container.remove();
      editorRef.current = null;
      containerRef.current = null;
    };
    // oxlint-disable-next-line react/exhaustive-deps
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    const editor = editorRef.current;
    if (!editorScopeInstance || !container || !editor) return;
    editorScopeInstance.attachRef(container);
    editorScopeInstance.setFocusDelegate(() => editor.focus());
    return () => {
      editorScopeInstance.setFocusDelegate(undefined);
      editorScopeInstance.attachRef(null);
    };
  }, [editorScopeInstance]);

  // ---------------------------------------------------------------------------
  // Model attachment — autorun that re-evaluates whenever the pane-local active
  // file or its OpenFileStore buffer handle changes.
  // ---------------------------------------------------------------------------
  useEffect(
    () =>
      autorun(() => {
        const editor = editorRef.current;
        if (!editor) return;
        const binder = installMonacoFacetBinder();

        const resource = getActiveFileResource(paneTabManager); // reactive
        // The buffer handle appears once the store has content and disappears
        // on teardown/re-key; handleFor reads an observable map, so this
        // autorun re-fires exactly when attachability changes.
        const handle = resource?.ref ? resource.entry?.handleFor(BUFFER) : undefined; // reactive
        const newBufUri = resource?.ref && handle ? encodeFacetUri(resource.ref, BUFFER) : null;

        if (!newBufUri) {
          // detach saves the file's view state, so the scroll position survives
          // switching to a non-file tab (conversation, diff, …).
          binder.detach(editor, prevBufUriRef.current);
          prevBufUriRef.current = undefined;
          return;
        }

        binder.attach(editor, newBufUri, prevBufUriRef.current);
        prevBufUriRef.current = newBufUri;

        const selectionRequest = resource?.selectionRequest;
        if (selectionRequest) {
          const { lineNumber, startColumn, endColumn } = selectionRequest.selection;
          const selection = {
            startLineNumber: lineNumber,
            startColumn,
            endLineNumber: lineNumber,
            endColumn,
          };
          editor.setSelection(selection);
          editor.revealRangeInCenter(selection);
          editor.focus();
          resource?.consumeSelectionRequest(selectionRequest.id);
        }

        // Satisfy any focus request that arrived while the model was still loading.
        if (focusPendingRef.current) {
          focusPendingRef.current = false;
          editor.focus();
        }
      }),
    // oxlint-disable-next-line react/exhaustive-deps
    []
  );

  // ---------------------------------------------------------------------------
  // Restore — re-apply crash-recovery buffer content for persisted open tabs.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!taskId) return;
    void editorView.restoreBuffers();
    // oxlint-disable-next-line react/exhaustive-deps
  }, [taskId]);

  // ---------------------------------------------------------------------------
  // Conflict dialog — reaction on pendingConflictPath shows the modal.
  // ---------------------------------------------------------------------------
  useEffect(
    () =>
      autorun(() => {
        const filePath = editorView.pendingConflictPath; // reactive
        if (!filePath) return;
        if (!editorView.openFilePaths.includes(filePath)) return;
        void (async () => {
          const outcome = await openConflictModal({ filePath });
          if (outcome.success) {
            void editorView.resolveConflict(outcome.data);
          }
        })();
      }),
    // oxlint-disable-next-line react/exhaustive-deps
    []
  );

  // ---------------------------------------------------------------------------
  // Focus restore — when this task becomes active and focusedRegion is 'main',
  // focus Monaco if a model is loaded; otherwise queue the intent.
  // ---------------------------------------------------------------------------
  const focusedRegion = taskView.focusedRegion;
  useEffect(() => {
    if (!isActive || focusedRegion !== 'main') return;
    // Only the focused pane should attempt to focus.
    if (paneLayout.activePaneId !== paneId) return;
    const editor = editorRef.current;
    if (editor?.getModel()) {
      editor.focus();
    } else {
      focusPendingRef.current = true;
    }
  }, [isActive, focusedRegion, paneId, paneLayout.activePaneId]);

  // ---------------------------------------------------------------------------
  // setEditorHost — called by PaneContent to give the editor a stable DOM node.
  // ---------------------------------------------------------------------------
  const setEditorHost = useCallback((el: HTMLElement | null) => {
    hostRef.current = el;
    const container = containerRef.current;
    const editor = editorRef.current;
    if (el && container && editor) {
      el.appendChild(container);
      editor.layout();
    }
  }, []);

  return (
    <ViewScopeInstanceProvider instance={editorScopeInstance}>
      <EditorContext.Provider value={{ setEditorHost }}>{children}</EditorContext.Provider>
    </ViewScopeInstanceProvider>
  );
});
