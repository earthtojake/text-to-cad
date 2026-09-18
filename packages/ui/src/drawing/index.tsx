import { Excalidraw, MainMenu, CaptureUpdateAction, convertToExcalidrawElements, exportToBlob, serializeAsJSON, viewportCoordsToSceneCoords } from '@excalidraw/excalidraw';
import type { AppState, BinaryFiles, ExcalidrawImperativeAPI, ExcalidrawInitialDataState } from '@excalidraw/excalidraw/types';
import type { ExcalidrawElement, FileId } from '@excalidraw/excalidraw/element/types';
import { emptyDrawingDocument, MAX_DRAWING_BYTES, parseDrawingScene } from '@hardcore/core/drawing';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import '@excalidraw/excalidraw/index.css';
import './styles.css';

export interface DrawingController {
  /** An in-memory snapshot for remounting the same temporary sketch. */
  serialize(): string;
  /** Snapshots synchronously, then encodes. Never reads a later scene after awaiting. */
  exportPng(options?: { background?: boolean }): Promise<Blob>;
}
export interface DrawingEditorProps {
  /** Retained in-memory snapshot of this sketch, never a file-import route. */
  initialScene?: string | null;
  name?: string;
  /** Transparent screen-space ink for a host-owned frozen viewport/background. */
  mode?: 'canvas' | 'overlay';
  onReady(controller: DrawingController | null): void;
  onContentChange?(hasContent: boolean): void;
}

/** Render a retained temporary scene without mounting or focusing its editor. */
export async function exportDrawingScenePng(serialized: string): Promise<Blob> {
  const scene = parseDrawingScene(serialized);
  const elements = scene.elements.filter(element => !element.isDeleted) as unknown as ExcalidrawElement[];
  if (!elements.length) throw new Error('Draw something before capturing the drawing.');
  return exportToBlob({ elements, files: scene.files as BinaryFiles,
    appState: { ...scene.appState, viewBackgroundColor: '#ffffff', exportBackground: true, exportWithDarkMode: false },
    mimeType: 'image/png', exportPadding: 24, maxWidthOrHeight: 2048 });
}

/** An editor only: no app detection, persistence, network, file dialogs or prompt routing. */
export function DrawingEditor({ initialScene, name = 'Drawing', mode = 'canvas', onReady, onContentChange }: DrawingEditorProps) {
  const [initialData] = useState(() => {
    const document = initialScene ? parseDrawingScene(initialScene) : emptyDrawingDocument();
    return { ...document, appState: { currentItemFontFamily: 5, ...document.appState,
      viewBackgroundColor: mode === 'overlay' ? 'transparent' : '#ffffff',
      exportBackground: mode !== 'overlay', exportWithDarkMode: false,
    } } as unknown as ExcalidrawInitialDataState;
  });
  // The SDK palette uses its own window capture listener and includes file
  // actions that ignore UIOptions. Register before its passive effect does.
  useLayoutEffect(() => {
    const blockPalette = (event: KeyboardEvent) => {
      if (!event.altKey && (event.metaKey || event.ctrlKey)
        && ((event.shiftKey && event.key.toLowerCase() === 'p') || event.key === '/')) {
        event.preventDefault(); event.stopImmediatePropagation();
      }
    };
    window.addEventListener('keydown', blockPalette, { capture: true });
    return () => window.removeEventListener('keydown', blockPalette, { capture: true });
  }, []);
  const ready = useRef(onReady);
  ready.current = onReady;
  // Excalidraw clears its imperative scene before parent passive cleanup.
  // Retain immutable scene references, not its API, for that final snapshot.
  const latest = useRef<{ elements: readonly ExcalidrawElement[]; appState: AppState; files: BinaryFiles } | null>(null);
  const [api, setApi] = useState<ExcalidrawImperativeAPI | null>(null);
  const liveApi = useRef<ExcalidrawImperativeAPI | null>(null);
  useEffect(() => {
    if (!api) return;
    liveApi.current = api;
    // Menu flags alone leave shortcuts and palette actions active. Disable
    // persistence, export, library and the redundant help/palette routes too.
    for (const name of ['saveFileToDisk', 'saveToActiveFile', 'loadScene',
      'copyAsPng', 'copyAsSvg', 'addToLibrary', 'toggleShortcuts', 'commandPalette',
      'toggleTheme', 'changeViewBackgroundColor'] as const) api.registerAction({
      name, label: '', trackEvent: false, perform: () => false, predicate: () => false,
    });
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
    return () => { liveApi.current = null; ready.current(null); };
  }, [api, mode]);
  const change = useCallback<NonNullable<Parameters<typeof Excalidraw>[0]['onChange']>>((elements, appState, files) => {
    latest.current = { elements, appState, files };
    onContentChange?.(elements.some(element => !element.isDeleted));
  }, [onContentChange]);
  const insertDroppedImage = async (file: File, clientX: number, clientY: number) => {
    if (!api) return;
    try {
      if (!['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.type) || file.size > MAX_DRAWING_BYTES) {
        throw new Error('Choose a PNG, JPEG, GIF or WebP image smaller than 20 MiB.');
      }
      const dataURL = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('The image could not be read.'));
        reader.readAsDataURL(file);
      });
      const image = new Image();
      image.src = dataURL;
      await image.decode();
      if (liveApi.current !== api) return;
      const state = api.getAppState();
      const point = viewportCoordsToSceneCoords({ clientX, clientY }, state);
      const scale = Math.min(1, 600 / Math.max(image.naturalWidth, image.naturalHeight));
      const width = image.naturalWidth * scale;
      const height = image.naturalHeight * scale;
      const fileId = crypto.randomUUID() as FileId;
      const elements = convertToExcalidrawElements([{ type: 'image', fileId,
        x: point.x - width / 2, y: point.y - height / 2, width, height, status: 'saved' }]);
      api.addFiles([{ id: fileId, dataURL: dataURL as BinaryFiles[string]['dataURL'], mimeType: file.type as BinaryFiles[string]['mimeType'], created: Date.now() }]);
      api.updateScene({ elements: [...api.getSceneElements(), ...elements],
        appState: { selectedElementIds: Object.fromEntries(elements.map(element => [element.id, true])) },
        captureUpdate: CaptureUpdateAction.IMMEDIATELY });
    } catch (error) {
      if (liveApi.current === api) api.setToast({ message: error instanceof Error ? error.message : 'The image could not be inserted.' });
    }
  };
  return <div className="hardcore-drawing-editor" data-drawing-mode={mode}
    onDropCapture={event => {
      // The SDK restores scene metadata embedded in PNGs as well as JSON files.
      // Insert dropped rasters directly so a drop can never replace this sketch.
      if (!event.dataTransfer.files.length && !event.dataTransfer.types.some(type => /excalidraw|json/i.test(type))) return;
      event.preventDefault(); event.stopPropagation();
      const file = event.dataTransfer.files[0];
      if (file) void insertDroppedImage(file, event.clientX, event.clientY);
    }}
    onPasteCapture={event => {
      const data = event.clipboardData;
      const file = data.files[0];
      let scene = false;
      try { scene = JSON.parse(data.getData('text/plain')).type === 'excalidraw'; } catch { /* Ordinary text and copied elements are supported. */ }
      if ((file && !['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.type)) || scene
        || data.types.some(type => /excalidrawlib|application\/vnd\.excalidraw\+json/i.test(type))) {
        event.preventDefault(); event.stopPropagation();
      }
    }}
    onKeyDownCapture={event => {
      const target = event.target as HTMLElement;
      const writable = target.matches('input, textarea, [contenteditable="true"]');
      const key = event.key.toLowerCase();
      const shortcut = !event.altKey && (event.metaKey || event.ctrlKey)
        && (key === 's' || key === 'o' || (event.shiftKey && key === 'e'));
      if (!shortcut && !(key === '?' && !writable)) return;
      event.preventDefault(); event.stopPropagation();
    }}>
    <Excalidraw initialData={initialData} excalidrawAPI={setApi} theme="light" name={name}
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
        saveAsImage: false, toggleTheme: false, changeViewBackgroundColor: false } }}>
      <MainMenu><MainMenu.DefaultItems.ClearCanvas /></MainMenu>
    </Excalidraw>
  </div>;
}
