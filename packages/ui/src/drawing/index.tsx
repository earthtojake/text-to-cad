import { Excalidraw, CaptureUpdateAction, convertToExcalidrawElements, exportToBlob, newElementWith, serializeAsJSON, viewportCoordsToSceneCoords } from '@excalidraw/excalidraw';
import type { AppState, BinaryFiles, ExcalidrawImperativeAPI, ExcalidrawInitialDataState } from '@excalidraw/excalidraw/types';
import type { ExcalidrawElement, FileId } from '@excalidraw/excalidraw/element/types';
import { emptyDrawingDocument, MAX_DRAWING_BYTES, parseDrawingScene } from '@hardcore/core/drawing';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useDrawingSession } from './session.js';
import { DEFAULT_OVERLAY_DRAWING_COLOR, DRAWING_TOOLS, DrawingToolbar } from './toolbar.jsx';
import type { DrawingTool } from './toolbar.jsx';
import { fillElementAt } from './fill';
import '@excalidraw/excalidraw/index.css';
import './styles.css';

export { DRAWING_COLORS, DRAWING_TOOLS, DrawingToolbar } from './toolbar.jsx';
export type { DrawingTool } from './toolbar.jsx';
export { useDrawingSession } from './session.js';
export type { DrawingSession } from './session.js';
/** Scene-to-screen mapping: a scene point `s` is drawn at `(s + scroll) * zoom` CSS pixels from the editor's top-left. */
export interface DrawingViewport { scrollX: number; scrollY: number; zoom: number }
export interface DrawingController {
  /** An in-memory snapshot for remounting the same temporary sketch. */
  serialize(): string;
  /** Snapshots synchronously, then encodes. Never reads a later scene after awaiting. */
  exportPng(options?: { background?: boolean }): Promise<Blob>;
  setTool(tool: DrawingTool): void;
  /** The color of what is drawn next. Existing ink keeps its own, selected or not. */
  setColor(color: string): void;
  undo(): void;
  redo(): void;
  /** Undoable, unlike unmounting the editor. */
  clear(): void;
  /** The committed ink exactly as displayed: viewport-sized and viewport-aligned, without selection handles. */
  inkCanvas(): HTMLCanvasElement | null;
}
export interface DrawingEditorProps {
  /** Retained in-memory snapshot of this sketch, never a file-import route. */
  initialScene?: string | null;
  name?: string;
  /** Transparent screen-space ink for a host-owned frozen viewport/background. */
  mode?: 'canvas' | 'overlay';
  /** `false` when the host places `DrawingToolbar` itself (the CAD viewport, beside its other tools). */
  toolbar?: boolean;
  /** The tool a new editor opens on; the SDK's own default is selection. */
  initialTool?: DrawingTool;
  onReady(controller: DrawingController | null): void;
  onContentChange?(hasContent: boolean): void;
  onToolChange?(tool: string): void;
  onColorChange?(color: string): void;
  /** Pan and zoom made inside the editor, for a host that moves its own background with the ink. */
  onViewportChange?(viewport: DrawingViewport): void;
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

function pressHistoryKey(editor: HTMLElement | null, redo: boolean) {
  const target = editor?.querySelector<HTMLElement>('.excalidraw');
  if (!target) return;
  target.focus({ preventScroll: true });
  const mac = /Mac|iP(hone|ad|od)/.test(navigator.platform);
  target.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', code: 'KeyZ', bubbles: true, cancelable: true,
    shiftKey: redo, metaKey: mac, ctrlKey: !mac }));
}

/** An editor only: no app detection, persistence, network, file dialogs or prompt routing. */
export function DrawingEditor({ initialScene, name = 'Drawing', mode = 'canvas', toolbar = true, initialTool = 'selection', onReady, onContentChange, onToolChange, onColorChange, onViewportChange }: DrawingEditorProps) {
  const [initialData] = useState(() => {
    const document = initialScene ? parseDrawingScene(initialScene) : emptyDrawingDocument();
    // Ink over someone else's picture cannot assume a light background.
    const overlayInk = mode === 'overlay' ? { currentItemStrokeColor: DEFAULT_OVERLAY_DRAWING_COLOR, currentItemStrokeWidth: 2 } : {};
    // Locked: a tool stays chosen after each shape, as the pen always has, rather
    // than handing every new line back to selection.
    const tool = { activeTool: { type: DRAWING_TOOLS.includes(initialTool) ? initialTool : 'selection', customType: null, locked: true, lastActiveTool: null } };
    return { ...document, appState: { currentItemFontFamily: 5, ...overlayInk, ...document.appState, ...tool,
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
  const root = useRef<HTMLDivElement | null>(null);
  const session = useDrawingSession(true, { tool: initialTool, color: mode === 'overlay' ? DEFAULT_OVERLAY_DRAWING_COLOR : '#1e1e1e' });
  const toolChange = useRef(onToolChange), colorChange = useRef(onColorChange), viewportChange = useRef(onViewportChange);
  const last = useRef({ tool: '', color: '' });
  toolChange.current = onToolChange; colorChange.current = onColorChange; viewportChange.current = onViewportChange;
  // The SDK paints its default white page until the scene it was given is in
  // place; over a viewport that is a white flash, so the surface waits for it.
  const [initialized, setInitialized] = useState(false);
  // Fill is this editor's tool, not the SDK's: a press with it active fills the area under the pointer.
  useEffect(() => api?.onPointerDown((activeTool, pointer) => {
    if (activeTool.type !== 'custom' || activeTool.customType !== 'fill') return;
    const state = api.getAppState();
    void fillElementAt(pointer.origin, { elements: api.getSceneElements(), appState: state, files: api.getFiles() }, state.currentItemStrokeColor)
      .then(fill => {
        if (liveApi.current !== api) return;
        if (!fill) { api.setToast({ message: 'Draw around an area first, then fill inside it.', duration: 2500 }); return; }
        // Appended: an insertion below existing elements re-indexes them, which the SDK
        // records as a second, invisible undo step. The outline is the fill's edge anyway.
        api.updateScene({ elements: [...api.getSceneElements(), fill], captureUpdate: CaptureUpdateAction.IMMEDIATELY });
      }).catch(() => { if (liveApi.current === api) api.setToast({ message: 'That area could not be filled.' }); });
  }), [api]);
  useEffect(() => api?.onScrollChange((scrollX, scrollY, zoom) => viewportChange.current?.({ scrollX, scrollY, zoom: zoom.value })), [api]);
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
      setTool(tool) {
        if (!DRAWING_TOOLS.includes(tool)) return;
        api.setActiveTool(tool === 'fill' ? { type: 'custom', customType: 'fill', locked: true } : { type: tool, locked: true });
      },
      setColor(color) { api.updateScene({ appState: { currentItemStrokeColor: color }, captureUpdate: CaptureUpdateAction.NEVER }); },
      // History is not part of the SDK's imperative API; its own shortcuts are.
      undo() { pressHistoryKey(root.current, false); },
      redo() { pressHistoryKey(root.current, true); },
      clear() {
        // A versioned deletion: the SDK's history ignores elements whose version did not move.
        api.updateScene({ elements: api.getSceneElements().map(element => newElementWith(element, { isDeleted: true })),
          appState: { selectedElementIds: {} }, captureUpdate: CaptureUpdateAction.IMMEDIATELY });
      },
      inkCanvas() { return root.current?.querySelector<HTMLCanvasElement>('canvas.excalidraw__canvas.static') ?? null; },
    };
    session.onReady(controller);
    ready.current(controller);
    return () => { liveApi.current = null; session.onReady(null); ready.current(null); };
  }, [api, mode, session.onReady]);
  const change = useCallback<NonNullable<Parameters<typeof Excalidraw>[0]['onChange']>>((elements, appState, files) => {
    latest.current = { elements, appState, files };
    const hasContent = elements.some(element => !element.isDeleted);
    onContentChange?.(hasContent);
    session.onContentChange(hasContent);
    setInitialized(true);
    const tool = appState.activeTool.type === 'custom' ? appState.activeTool.customType ?? 'custom' : appState.activeTool.type;
    const color = appState.currentItemStrokeColor;
    if (last.current.tool !== tool) { last.current.tool = tool; session.onToolChange(tool); toolChange.current?.(tool); }
    if (color && last.current.color !== color) { last.current.color = color; session.onColorChange(color); colorChange.current?.(color); }
  }, [onContentChange, session.onContentChange, session.onToolChange, session.onColorChange]);
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
  return <div ref={root} className="hardcore-drawing-editor" data-drawing-mode={mode} data-drawing-ready={initialized ? '' : undefined}
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
      // The toolbar offers DRAWING_TOOLS only; the SDK's keys for its other tools would leave it showing none.
      const hiddenTool = !writable && !event.altKey && !event.metaKey && !event.ctrlKey
        && ['q', 'k', 'f', 'd', '3', '9'].includes(key);
      if (!shortcut && !hiddenTool && !(key === '?' && !writable)) return;
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
        saveAsImage: false, toggleTheme: false, changeViewBackgroundColor: false } }} />
    {toolbar ? <DrawingToolbar drawing={session} className="hardcore-drawing-editor__toolbar" /> : null}
  </div>;
}
