import { useEffect } from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DrawingEditor, exportDrawingScenePng } from './index';
import type { DrawingController } from './index';

const sdk = vi.hoisted(() => ({ props: null as any, export: vi.fn(), api: null as any, actions: {} as Record<string, any>, scroll: null as any, pointerDown: null as any, canvas: vi.fn() }));
vi.mock('@excalidraw/excalidraw', async () => {
  const React = await import('react');
  class Canvas extends React.Component<any> {
    componentDidMount() {
      sdk.props = this.props;
      const elements = [{ id: 'rectangle', type: 'rectangle', x: 0, y: 0, width: 20, height: 20 }];
      const appState = { scrollX: 11, scrollY: 22, zoom: { value: 1 }, viewBackgroundColor: '#fff', activeTool: { type: 'selection' }, currentItemStrokeColor: '#1e1e1e' };
      sdk.api = { getSceneElements: () => elements, getAppState: () => appState, getFiles: () => ({}),
        addFiles: vi.fn(), updateScene: vi.fn(), setActiveTool: vi.fn(),
        onScrollChange: (listener: any) => { sdk.scroll = listener; return () => { sdk.scroll = null; }; },
        onPointerDown: (listener: any) => { sdk.pointerDown = listener; return () => { sdk.pointerDown = null; }; }, registerAction: (action: any) => { sdk.actions[action.name] = action; }, setToast: vi.fn() };
      this.props.onChange(elements, appState, {});
      this.props.excalidrawAPI(sdk.api);
    }
    componentWillUnmount() {
      // Matches the real SDK: imperative state is cleared during commit,
      // before a parent's passive cleanup captures the departing scene.
      sdk.api.getSceneElements = () => [];
      sdk.api.getFiles = () => ({});
    }
    render() { return null; }
  }
  return { Excalidraw: Canvas, exportToBlob: sdk.export, exportToCanvas: sdk.canvas,
    getCommonBounds: (elements: any[]) => [Math.min(...elements.map(e => e.x)), Math.min(...elements.map(e => e.y)),
      Math.max(...elements.map(e => e.x + e.width)), Math.max(...elements.map(e => e.y + e.height))],
    CaptureUpdateAction: { IMMEDIATELY: 'IMMEDIATELY', NEVER: 'NEVER' },
    newElementWith: (element: any, updates: any) => ({ ...element, ...updates, version: (element.version ?? 1) + 1 }),
    viewportCoordsToSceneCoords: (point: any) => ({ x: point.clientX, y: point.clientY }),
    convertToExcalidrawElements: (elements: any[]) => elements.map(element => ({ ...element, id: `${element.type}-element` })),
    serializeAsJSON: (elements: unknown, appState: unknown, files: unknown) => JSON.stringify({ type: 'excalidraw', version: 2, elements, appState, files }) };
});
afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals(); });

describe('drawing editor', () => {
  it('rejects scene file drops and paste while retaining normal copied ink and raster images', async () => {
    const view = render(<DrawingEditor onReady={() => {}} />);
    await waitFor(() => expect(sdk.props).not.toBeNull());
    await expect(sdk.props.generateIdForFile(new File(['<svg/>'], 'drawing.svg', { type: 'image/svg+xml' }))).rejects.toThrow('PNG');
    expect(sdk.props.onPaste({ elements: [{ id: 'remote', type: 'embeddable', x: 0, y: 0, width: 10, height: 10 }] })).toBe(false);
    expect(sdk.props.onPaste({ elements: [{ id: 'ink', type: 'rectangle', x: 0, y: 0, width: 10, height: 10 }] })).toBe(true);
    const file = new File(['{}'], 'plan.excalidraw', { type: 'application/json' });
    expect(fireEvent.drop(view.container.firstChild!, { dataTransfer: { files: [file], types: ['Files'] } })).toBe(false);
    expect(sdk.api.getSceneElements()[0].id).toBe('rectangle');
    const clipboardData = { files: [file], types: ['Files'], getData: () => '' };
    expect(fireEvent.paste(view.container.firstChild!, { clipboardData })).toBe(false);
    expect(fireEvent.paste(view.container.firstChild!, { clipboardData: { files: [], types: ['text/plain'],
      getData: () => JSON.stringify({ type: 'excalidraw', elements: [] }) } })).toBe(false);
    expect(fireEvent.paste(view.container.firstChild!, { clipboardData: { files: [], types: ['text/plain'], getData: () => 'A dimension' } })).toBe(true);
    expect(fireEvent.paste(view.container.firstChild!, { clipboardData: { files: [new File(['png'], 'image.png', { type: 'image/png' })],
      types: ['Files'], getData: () => '' } })).toBe(true);
    view.unmount();
  });
  it('inserts a raster drop as an undoable image without loading its embedded scene', async () => {
    vi.stubGlobal('Image', class {
      naturalWidth = 1200;
      naturalHeight = 800;
      src = '';
      decode = async () => {};
    });
    const view = render(<DrawingEditor onReady={() => {}} />);
    await waitFor(() => expect(sdk.api.addFiles).toBeDefined());
    const file = new File(['PNG with scene metadata'], 'sketch.png', { type: 'image/png' });
    fireEvent.drop(view.container.firstChild!, { clientX: 100, clientY: 200,
      dataTransfer: { files: [file], types: ['Files'] } });
    await waitFor(() => expect(sdk.api.updateScene).toHaveBeenCalledTimes(1));
    expect(sdk.api.addFiles.mock.calls[0][0][0]).toMatchObject({ mimeType: 'image/png' });
    expect(sdk.api.updateScene.mock.calls[0][0]).toMatchObject({ elements: [
      { id: 'rectangle' }, { type: 'image', width: 600, height: 400, status: 'saved' },
    ], captureUpdate: 'IMMEDIATELY' });
    view.unmount();
  });
  it('disables save/load, export, library, help and palette routes and always uses a white light canvas', async () => {
    const view = render(<DrawingEditor initialScene={JSON.stringify({ type: 'excalidraw', version: 2, elements: [], appState: { viewBackgroundColor: '#000' } })} onReady={() => {}} />);
    await waitFor(() => expect(sdk.actions.saveFileToDisk).toBeDefined());
    for (const name of ['saveFileToDisk', 'saveToActiveFile', 'loadScene', 'copyAsPng', 'copyAsSvg', 'addToLibrary', 'toggleShortcuts', 'commandPalette']) {
      expect(sdk.actions[name].perform()).toBe(false);
      expect(sdk.actions[name].predicate()).toBe(false);
    }
    expect(fireEvent.keyDown(view.container.firstChild!, { key: 'S', metaKey: true, shiftKey: true })).toBe(false);
    expect(fireEvent.keyDown(view.container.firstChild!, { key: 'o', ctrlKey: true })).toBe(false);
    expect(fireEvent.keyDown(view.container.firstChild!, { key: 'e', metaKey: true, shiftKey: true })).toBe(false);
    expect(fireEvent.keyDown(view.container.firstChild!, { key: '/', metaKey: true })).toBe(false);
    expect(fireEvent.keyDown(view.container.firstChild!, { key: 'p', ctrlKey: true, shiftKey: true })).toBe(false);
    expect(fireEvent.keyDown(view.container.firstChild!, { key: '?' })).toBe(false);
    expect(sdk.props.theme).toBe('light');
    expect(sdk.props.initialData.appState.viewBackgroundColor).toBe('#ffffff');
    expect(sdk.props.UIOptions.canvasActions.changeViewBackgroundColor).toBe(false);
    view.unmount();
  });
  it('retains final ink after SDK teardown, without serializing each change', async () => {
    let controller: DrawingController | null = null;
    let departing = '';
    function Host() {
      useEffect(() => () => { departing = controller!.serialize(); }, []);
      return <DrawingEditor onReady={value => { if (value) controller = value; }} />;
    }
    const view = render(<Host />);
    await waitFor(() => expect(controller).not.toBeNull());
    view.unmount();
    expect(JSON.parse(departing).elements[0].id).toBe('rectangle');
    expect(JSON.parse(departing).appState.scrollX).toBe(11);
    expect(sdk.api.getSceneElements()).toEqual([]);
  });
  it('captures retained ink without mounting an editor and rejects an empty scene', async () => {
    sdk.export.mockResolvedValue(new Blob(['image'], { type: 'image/png' }));
    await exportDrawingScenePng(JSON.stringify({ type: 'excalidraw', version: 2,
      elements: [{ id: 'ink', type: 'rectangle', x: 0, y: 0, width: 20, height: 20 }],
      appState: { viewBackgroundColor: '#000000' } }));
    expect(sdk.export.mock.calls[0][0]).toMatchObject({ elements: [{ id: 'ink' }],
      appState: { viewBackgroundColor: '#ffffff', exportBackground: true, exportWithDarkMode: false }, maxWidthOrHeight: 2048 });
    await expect(exportDrawingScenePng(JSON.stringify({ type: 'excalidraw', version: 2, elements: [] }))).rejects.toThrow('Draw something');
  });
  it('captures PNG input before async encoding and supports transparent overlay ink', async () => {
    let controller: DrawingController | null = null;
    sdk.export.mockResolvedValue(new Blob(['image'], { type: 'image/png' }));
    const view = render(<DrawingEditor mode="overlay" onReady={value => { controller = value; }} />);
    await waitFor(() => expect(controller).not.toBeNull());
    const pending = controller!.exportPng();
    sdk.api.getSceneElements()[0].width = 100;
    await pending;
    expect(sdk.export.mock.calls[0][0]).toMatchObject({ elements: [{ width: 20 }],
      appState: { exportBackground: false, exportWithDarkMode: false }, maxWidthOrHeight: 2048 });
    expect(sdk.props.handleKeyboardGlobally).toBe(false);
    view.unmount();
  });
  it('lets a host toolbar drive an overlay: sticky tools, color, history, an undoable clear and the viewport', async () => {
    let controller: DrawingController | null = null;
    const onToolChange = vi.fn(), onColorChange = vi.fn(), onViewportChange = vi.fn();
    const view = render(<DrawingEditor mode="overlay" toolbar={false} initialTool="freedraw"
      onReady={value => { controller = value; }} onToolChange={onToolChange} onColorChange={onColorChange} onViewportChange={onViewportChange} />);
    await waitFor(() => expect(controller).not.toBeNull());
    const editor = view.container.firstChild as HTMLElement;
    expect(view.container.querySelector('[aria-label="Drawing tools"]')).toBeNull();
    // Locked: a line is followed by another line, as a pen stroke always was by another stroke.
    expect(sdk.props.initialData.appState).toMatchObject({ viewBackgroundColor: 'transparent', currentItemStrokeColor: '#ff2d55',
      activeTool: { type: 'freedraw', locked: true }, currentItemStrokeWidth: 2 / 4.25 });
    // The SDK paints a white page until the given scene is in place; the overlay stays hidden until then.
    expect(editor.dataset.drawingReady).toBe('');

    controller!.setTool('arrow');
    expect(sdk.api.updateScene).toHaveBeenLastCalledWith({ appState: { currentItemStrokeWidth: 2 }, captureUpdate: 'NEVER' });
    expect(sdk.api.setActiveTool).toHaveBeenLastCalledWith({ type: 'arrow', locked: true });
    controller!.setTool('hand');
    expect(sdk.api.setActiveTool).toHaveBeenLastCalledWith({ type: 'hand', locked: true });
    // The SDK's lock, image, frame, embed and laser tools are not the toolbar's to offer.
    controller!.setTool('laser' as any);
    expect(sdk.api.setActiveTool).toHaveBeenCalledTimes(2);
    for (const key of ['q', 'k', 'f', 'd', '3', '9']) expect(fireEvent.keyDown(editor, { key })).toBe(false);
    for (const key of ['p', 'e', '0', 'v', 'h']) expect(fireEvent.keyDown(editor, { key })).toBe(true);

    // The color of what is drawn next: no element is touched, selected or not, and it is not an undo step.
    controller!.setColor('#39ff14');
    expect(sdk.api.updateScene).toHaveBeenLastCalledWith({ appState: { currentItemStrokeColor: '#39ff14' }, captureUpdate: 'NEVER' });

    // The SDK reports every tool and color change, whoever made it.
    expect(onToolChange).toHaveBeenLastCalledWith('selection');
    expect(onColorChange).toHaveBeenLastCalledWith('#1e1e1e');
    const next = { ...sdk.api.getAppState(), activeTool: { type: 'arrow' }, currentItemStrokeColor: '#39ff14' };
    sdk.props.onChange(sdk.api.getSceneElements(), next, {});
    sdk.props.onChange(sdk.api.getSceneElements(), next, {});
    expect(onToolChange.mock.calls).toEqual([['selection'], ['arrow']]);
    expect(onColorChange.mock.calls).toEqual([['#1e1e1e'], ['#39ff14']]);

    sdk.scroll(40, -12, { value: 1.5 });
    expect(onViewportChange).toHaveBeenLastCalledWith({ scrollX: 40, scrollY: -12, zoom: 1.5 });

    // History has no imperative API: the editor's own shortcut is pressed on its canvas container.
    const surface = document.createElement('div');
    surface.className = 'excalidraw'; surface.tabIndex = -1;
    editor.appendChild(surface);
    const keys: KeyboardEvent[] = [];
    surface.addEventListener('keydown', event => keys.push(event));
    controller!.undo(); controller!.redo();
    expect(keys.map(event => [event.key, event.shiftKey, event.metaKey || event.ctrlKey])).toEqual([['z', false, true], ['z', true, true]]);

    controller!.clear();
    expect(sdk.api.updateScene).toHaveBeenLastCalledWith({ elements: [expect.objectContaining({ id: 'rectangle', isDeleted: true, version: 2 })],
      appState: { selectedElementIds: {} }, captureUpdate: 'IMMEDIATELY' });

    const ink = document.createElement('canvas');
    ink.className = 'excalidraw__canvas static';
    surface.appendChild(ink);
    expect(controller!.inkCanvas()).toBe(ink);
    view.unmount();
    expect(sdk.scroll).toBeNull();
  });
  it('the standalone editor carries the same toolbar, driving itself', async () => {
    const view = render(<DrawingEditor onReady={() => {}} />);
    await waitFor(() => expect(sdk.api?.setActiveTool).toBeDefined());
    const tools = await waitFor(() => { const group = view.container.querySelector('[aria-label="Drawing tools"]'); expect(group).not.toBeNull(); return group!; });
    const button = (name: string) => tools.querySelector<HTMLButtonElement>(`button[aria-label="${name}"]`)!;
    await waitFor(() => expect(button('Line').disabled).toBe(false));
    expect(sdk.props.initialData.appState).toMatchObject({ viewBackgroundColor: '#ffffff', activeTool: { type: 'selection', locked: true } });
    expect(sdk.props.initialData.appState.currentItemStrokeColor).toBeUndefined();
    expect(button('Select and move drawings').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(button('Line'));
    expect(sdk.api.setActiveTool).toHaveBeenLastCalledWith({ type: 'line', locked: true });
    fireEvent.click(button('Pan view'));
    expect(sdk.api.setActiveTool).toHaveBeenLastCalledWith({ type: 'hand', locked: true });
    fireEvent.click(button('Color'));
    fireEvent.click(view.container.querySelector<HTMLButtonElement>('[role="radio"][aria-label="Neon cyan"]')!);
    expect(sdk.api.updateScene).toHaveBeenLastCalledWith({ appState: { currentItemStrokeColor: '#00e5ff' }, captureUpdate: 'NEVER' });
    fireEvent.click(button('Clear drawing'));
    expect(sdk.api.updateScene).toHaveBeenLastCalledWith(expect.objectContaining({ captureUpdate: 'IMMEDIATELY' }));
    view.unmount();
  });
  it('fills the area inside drawn ink with a translucent, undoable element of the current color', async () => {
    let controller: DrawingController | null = null;
    const view = render(<DrawingEditor mode="overlay" toolbar={false} onReady={value => { controller = value; }} />);
    await waitFor(() => expect(controller).not.toBeNull());
    controller!.setTool('fill');
    expect(sdk.api.setActiveTool).toHaveBeenLastCalledWith({ type: 'custom', customType: 'fill', locked: true });
    // A 200 x 100 outline at (100, 50); the SDK's render of it, 12 px padded, at 420 / 224 scale.
    const outline = { id: 'outline', type: 'rectangle', x: 100, y: 50, width: 200, height: 100, angle: 0, strokeColor: '#ff2d55', backgroundColor: 'transparent' };
    const earlierFill = { id: 'old-fill', type: 'line', x: 0, y: 0, width: 900, height: 900, angle: 0, strokeColor: 'transparent', backgroundColor: '#39ff14', points: [[0, 0], [900, 0], [900, 900], [0, 0]] };
    sdk.api.getSceneElements = () => [earlierFill, outline];
    sdk.api.getAppState = () => ({ zoom: { value: 1 }, currentItemStrokeColor: '#00e5ff', activeTool: { type: 'custom', customType: 'fill' } });
    sdk.canvas.mockImplementation(async ({ elements, getDimensions, exportPadding }: any) => {
      // An earlier fill is never an outline: it would wall off, or swallow, every later one.
      expect(elements.map((element: any) => element.id)).toEqual(['outline']);
      const { width, height, scale } = getDimensions(200 + exportPadding * 2, 100 + exportPadding * 2);
      const data = new Uint8ClampedArray(width * height * 4);
      const [x0, y0, x1, y1] = [exportPadding, exportPadding, exportPadding + 200, exportPadding + 100].map(value => Math.round(value * scale));
      for (let y = y0; y <= y1; y += 1) for (let x = x0; x <= x1; x += 1) {
        if (x - x0 < 3 || x1 - x < 3 || y - y0 < 3 || y1 - y < 3) data[(y * width + x) * 4 + 3] = 255;
      }
      return { width, height, getContext: () => ({ getImageData: () => ({ data }) }) };
    });
    sdk.pointerDown({ type: 'custom', customType: 'fill' }, { origin: { x: 180, y: 90 } });
    await waitFor(() => expect(sdk.api.updateScene).toHaveBeenCalledTimes(1));
    const update = sdk.api.updateScene.mock.calls[0][0];
    expect(update.captureUpdate).toBe('IMMEDIATELY');
    // Appended, so one Undo removes it (an insertion below re-indexes the rest as a second step).
    expect(update.elements.map((element: any) => element.id)).toEqual(['old-fill', 'outline', 'line-element']);
    const fill = update.elements.at(-1);
    expect(fill).toMatchObject({ type: 'line', strokeColor: 'transparent', backgroundColor: '#00e5ff', fillStyle: 'solid', opacity: 35 });
    expect(fill.points[0]).toEqual(fill.points.at(-1));
    const xs = fill.points.map((point: number[]) => fill.x + point[0]), ys = fill.points.map((point: number[]) => fill.y + point[1]);
    for (const [value, expected] of [[Math.min(...xs), 100], [Math.max(...xs), 300], [Math.min(...ys), 50], [Math.max(...ys), 150]]) expect(Math.abs(value - expected)).toBeLessThan(4);

    // Outside any ink there is no area to mean: a hint, and no element.
    sdk.pointerDown({ type: 'custom', customType: 'fill' }, { origin: { x: 600, y: 600 } });
    await waitFor(() => expect(sdk.api.setToast).toHaveBeenCalledTimes(1));
    // Any other tool's press is the SDK's own business.
    sdk.pointerDown({ type: 'freedraw' }, { origin: { x: 180, y: 90 } });
    await new Promise(resolve => setTimeout(resolve, 20));
    expect(sdk.api.updateScene).toHaveBeenCalledTimes(1);
    view.unmount();
  });
});
