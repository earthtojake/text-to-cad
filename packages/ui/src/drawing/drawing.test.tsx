import { useEffect } from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DrawingEditor } from './index';
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
        registerAction: (action: any) => { sdk.actions[action.name] = action; }, setToast: vi.fn() };
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
    serializeAsJSON: (elements: unknown, appState: unknown, files: unknown) => JSON.stringify({ type: 'excalidraw', version: 2, elements, appState, files }) };
});
afterEach(() => vi.clearAllMocks());

describe('drawing editor', () => {
  it('rejects nonportable paste/images and delegates scene drops without replacing the current sketch', async () => {
    const imported = vi.fn();
    const view = render(<DrawingEditor theme="light" onReady={() => {}} onImportFile={imported} />);
    await waitFor(() => expect(sdk.props).not.toBeNull());
    await expect(sdk.props.generateIdForFile(new File(['<svg/>'], 'drawing.svg', { type: 'image/svg+xml' }))).rejects.toThrow('PNG');
    expect(sdk.props.onPaste({ elements: [{ id: 'remote', type: 'embeddable', x: 0, y: 0, width: 10, height: 10 }] })).toBe(false);
    const file = new File(['{}'], 'plan.excalidraw', { type: 'application/json' });
    fireEvent.drop(view.container.firstChild!, { dataTransfer: { files: [file] } });
    expect(imported).toHaveBeenCalledWith(file);
    expect(sdk.api.getSceneElements()[0].id).toBe('rectangle');
    view.unmount();
  });
  it('routes save shortcuts and palette actions through the host without giving the editor a file handle', async () => {
    const save = vi.fn(); const open = vi.fn();
    const view = render(<DrawingEditor theme="light" onReady={() => {}} onSaveCopy={save} onOpenFile={open} />);
    await waitFor(() => expect(sdk.actions.saveFileToDisk).toBeDefined());
    fireEvent.keyDown(view.container.firstChild!, { key: 'S', metaKey: true, shiftKey: true });
    expect(save).toHaveBeenCalledTimes(1);
    expect(sdk.actions.saveFileToDisk.perform()).toBe(false);
    expect(save).toHaveBeenCalledTimes(2);
    fireEvent.keyDown(view.container.firstChild!, { key: 'o', ctrlKey: true });
    expect(open).toHaveBeenCalledTimes(1);
    view.unmount();
  });
  it('retains final ink after SDK teardown, without serializing each change', async () => {
    let controller: DrawingController | null = null;
    let departing = '';
    function Host() {
      useEffect(() => () => { departing = controller!.serialize(); }, []);
      return <DrawingEditor theme="light" onReady={value => { if (value) controller = value; }} />;
    }
    const view = render(<Host />);
    await waitFor(() => expect(controller).not.toBeNull());
    view.unmount();
    expect(JSON.parse(departing).elements[0].id).toBe('rectangle');
    expect(JSON.parse(departing).appState.scrollX).toBe(11);
    expect(sdk.api.getSceneElements()).toEqual([]);
  });
  it('captures PNG input before async encoding and supports transparent overlay ink', async () => {
    let controller: DrawingController | null = null;
    sdk.export.mockResolvedValue(new Blob(['image'], { type: 'image/png' }));
    const view = render(<DrawingEditor theme="dark" mode="overlay" onReady={value => { controller = value; }} />);
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
