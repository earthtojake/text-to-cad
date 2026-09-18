import { Excalidraw, MainMenu, exportToBlob, serializeAsJSON } from '@excalidraw/excalidraw';
import type { AppState, BinaryFiles, ExcalidrawImperativeAPI, ExcalidrawInitialDataState } from '@excalidraw/excalidraw/types';
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types';
import { emptyDrawingDocument, MAX_DRAWING_BYTES, parseDrawingScene } from '@hardcore/core/drawing';
import { useCallback, useEffect, useRef, useState } from 'react';
import '@excalidraw/excalidraw/index.css';
import './styles.css';

export interface DrawingController {
  /** A self-contained .excalidraw document. Hosts decide whether to keep or save it. */
  serialize(): string;
  /** Snapshots synchronously, then encodes. Never reads a later scene after awaiting. */
  exportPng(options?: { background?: boolean }): Promise<Blob>;
}
export interface DrawingEditorProps {
  initialScene?: string | null;
  theme: 'light' | 'dark';
  name?: string;
  /** Transparent screen-space ink for a host-owned frozen viewport/background. */
  mode?: 'canvas' | 'overlay';
  onReady(controller: DrawingController | null): void;
  onContentChange?(hasContent: boolean): void;
  onSaveCopy?(): void;
  onOpenFile?(): void;
  onImportFile?(file: File): void;
}

/** An editor only: no app detection, persistence, network, file dialogs or prompt routing. */
export function DrawingEditor({ initialScene, theme, name = 'Drawing', mode = 'canvas', onReady, onContentChange, onSaveCopy, onOpenFile, onImportFile }: DrawingEditorProps) {
  const [initialData] = useState(() => {
    const document = initialScene ? parseDrawingScene(initialScene) : emptyDrawingDocument();
    return { ...document, appState: { currentItemFontFamily: 5, ...document.appState,
      ...(mode === 'overlay' ? { viewBackgroundColor: 'transparent' } : {}),
      exportBackground: mode !== 'overlay', exportWithDarkMode: false,
    } } as unknown as ExcalidrawInitialDataState;
  });
  const ready = useRef(onReady);
  ready.current = onReady;
  const hostActions = useRef({ onSaveCopy, onOpenFile, onImportFile });
  hostActions.current = { onSaveCopy, onOpenFile, onImportFile };
  // Excalidraw clears its imperative scene before parent passive cleanup.
  // Retain immutable scene references, not its API, for that final snapshot.
  const latest = useRef<{ elements: readonly ExcalidrawElement[]; appState: AppState; files: BinaryFiles } | null>(null);
  const [api, setApi] = useState<ExcalidrawImperativeAPI | null>(null);
  useEffect(() => {
    if (!api) return;
    // UIOptions hides menu items but does not disable Save-as's shortcut or
    // palette action. Override the public actions so every route uses the host.
    for (const name of ['saveFileToDisk', 'saveToActiveFile'] as const) api.registerAction({
      name, label: 'exportDialog.disk_title', trackEvent: false,
      perform: () => { hostActions.current.onSaveCopy?.(); return false; },
      keyTest: event => (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's',
    });
    api.registerAction({ name: 'loadScene', label: 'buttons.load', trackEvent: false,
      perform: () => { hostActions.current.onOpenFile?.(); return false; } });
    const controller: DrawingController = {
      serialize() {
        const { elements, appState: state, files } = latest.current ?? {
          elements: api.getSceneElements(), appState: api.getAppState(), files: api.getFiles(),
        };
        const document = JSON.parse(serializeAsJSON(elements, state, files, 'local'));
        document.appState = { ...document.appState, scrollX: state.scrollX, scrollY: state.scrollY, zoom: state.zoom };
        return JSON.stringify(document);
      },
      async exportPng({ background = mode !== 'overlay' } = {}) {
        const elements = structuredClone(api.getSceneElements());
        if (!elements.length) return Promise.reject(new Error('Draw something before adding it to the prompt.'));
        const files = structuredClone(api.getFiles());
        const appState = { ...api.getAppState(), exportBackground: background, exportWithDarkMode: false };
        return exportToBlob({ elements, files, appState, mimeType: 'image/png', exportPadding: 24, maxWidthOrHeight: 2048 });
      },
    };
    ready.current(controller);
    return () => ready.current(null);
  }, [api, mode]);
  const change = useCallback<NonNullable<Parameters<typeof Excalidraw>[0]['onChange']>>((elements, appState, files) => {
    latest.current = { elements, appState, files };
    onContentChange?.(elements.some(element => !element.isDeleted));
  }, [onContentChange]);
  return <div className="hardcore-drawing-editor" data-drawing-mode={mode}
    onDropCapture={event => {
      const scene = [...event.dataTransfer.files].find(file => /\.(?:excalidraw|json)$/i.test(file.name));
      if (!scene) return;
      event.preventDefault(); event.stopPropagation();
      hostActions.current.onImportFile?.(scene);
    }}
    onKeyDownCapture={event => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key !== 's' && key !== 'o') return;
      event.preventDefault(); event.stopPropagation();
      if (key === 's') hostActions.current.onSaveCopy?.();
      else hostActions.current.onOpenFile?.();
    }}>
    <Excalidraw initialData={initialData} excalidrawAPI={setApi} theme={theme} name={name}
      handleKeyboardGlobally={false} autoFocus={false} aiEnabled={false} validateEmbeddable={false}
      generateIdForFile={async file => {
        if (!['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.type) || file.size > MAX_DRAWING_BYTES) {
          throw new Error('Choose a PNG, JPEG, GIF or WebP image smaller than 20 MiB.');
        }
        const hash = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
        return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, '0')).join('');
      }}
      onPaste={data => {
        if (!data.elements) return true;
        try { parseDrawingScene(JSON.stringify({ ...emptyDrawingDocument(), elements: data.elements, files: data.files ?? {} })); }
        catch (error) { api?.setToast({ message: error instanceof Error ? error.message : 'Unsupported drawing content.' }); return false; }
        return true;
      }}
      onChange={change} onLinkOpen={(_element, event) => event.preventDefault()}
      UIOptions={{ canvasActions: { loadScene: false, saveToActiveFile: false, export: false,
        saveAsImage: false, toggleTheme: false, changeViewBackgroundColor: mode !== 'overlay' } }}>
      <MainMenu><MainMenu.DefaultItems.ClearCanvas /><MainMenu.DefaultItems.Help /></MainMenu>
    </Excalidraw>
  </div>;
}
