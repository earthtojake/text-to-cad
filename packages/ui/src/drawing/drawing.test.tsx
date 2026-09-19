import { useEffect } from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DrawingEditor, exportDrawingScenePng } from './index';
import type { DrawingController } from './index';

const sdk = vi.hoisted(() => ({ props: null as any, export: vi.fn(), api: null as any, actions: {} as Record<string, any> }));
vi.mock('@excalidraw/excalidraw', async () => {
  const React = await import('react');
  class Canvas extends React.Component<any> {
    componentDidMount() {
      sdk.props = this.props;
      const elements = [{ id: 'rectangle', type: 'rectangle', x: 0, y: 0, width: 20, height: 20 }];
      const appState = { scrollX: 11, scrollY: 22, zoom: { value: 1 }, viewBackgroundColor: '#fff' };
      sdk.api = { getSceneElements: () => elements, getAppState: () => appState, getFiles: () => ({}),
        addFiles: vi.fn(), updateScene: vi.fn(), registerAction: (action: any) => { sdk.actions[action.name] = action; }, setToast: vi.fn() };
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
  const Menu = Object.assign(() => null, { DefaultItems: { ClearCanvas: () => null, Help: () => null } });
  return { Excalidraw: Canvas, MainMenu: Menu, exportToBlob: sdk.export,
    CaptureUpdateAction: { IMMEDIATELY: 'IMMEDIATELY' },
    viewportCoordsToSceneCoords: (point: any) => ({ x: point.clientX, y: point.clientY }),
    convertToExcalidrawElements: (elements: any[]) => elements.map(element => ({ ...element, id: 'image-element' })),
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
});
