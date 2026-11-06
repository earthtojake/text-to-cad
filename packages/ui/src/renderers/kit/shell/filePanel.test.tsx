import { useRef, useState } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { unavailablePromptContext } from '@cad/core/prompt';
import { FileViewer, defineFileRenderer } from '../../../../dist/file-viewer/index.js';
import { useFlatPanelState } from '../../../../dist/renderers/kit/shell/FlatPanel.js';

// The view's panel is the file's (`filePanel.js`): kept in each file's view by the file viewer, written by
// the panel's own state (`useFlatPanelState`), whatever renderer draws the file.
let frameWidth = 1280;
const rect = Element.prototype.getBoundingClientRect;
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.getBoundingClientRect = function (this: Element) {
    return this.hasAttribute('data-frame') ? DOMRect.fromRect({ x: 0, y: 0, width: frameWidth, height: 700 }) : rect.call(this);
  };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Element.prototype.getBoundingClientRect = rect; frameWidth = 1280; });

// The tab's settings as the renderer reads them, and what it writes back.
let toolStack: any = { panels: {}, collapsed: {} };
const stackWrites: any[] = [];
function Panelled() {
  const frameRef = useRef<HTMLDivElement>(null);
  const flat = useFlatPanelState({ frameRef, mobile: false, enabled: true, kind: 'board', toolStack,
    onToolStackChange: (patch: any) => { stackWrites.push(patch); toolStack = { ...toolStack, ...(typeof patch === 'function' ? patch(toolStack) : patch) }; } });
  return <div ref={frameRef} data-frame="">
    <output data-testid="panel">{JSON.stringify({ open: flat.open, width: flat.width, tab: flat.tab ?? null, detail: flat.detailHeight })}</output>
    <button type="button" onClick={() => flat.control!.toggle()}>toggle</button>
    <button type="button" onClick={() => flat.changeWidth(300)}>300</button>
    <button type="button" onClick={() => flat.changeWidth(260)}>260</button>
    <button type="button" onClick={() => flat.changeTab('layers')}>layers</button>
  </div>;
}
const renderer = defineFileRenderer({ id: 'panelled', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
  load: async () => ({ default: Panelled }) });
const host = {
  files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop()!, kind: 'file' as const, extension: 'kicad_pcb', size: 1 }) },
  clipboard: { writeText: async () => {}, writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const }, navigation: { openFile(_path: string) {} },
};
const A = '/models/a.kicad_pcb', B = '/models/b.dxf';

/** A tab: the file viewer over a state the test keeps (`kept`), as a host's store keeps it through a reload. */
function tab(kept: { state: any }) {
  let show: (file: string) => void = () => {};
  function Tab() {
    const [file, setFile] = useState(A);
    const [state, setState] = useState(kept.state);
    show = setFile;
    kept.state = state;
    return <FileViewer file={file} host={host as any} renderers={[renderer]} state={state} onStateChange={next => { kept.state = next; setState(next); }} />;
  }
  const view = render(<Tab />);
  return { unmount: view.unmount, show: (file: string) => act(() => show(file)) };
}
const panel = async () => JSON.parse((await screen.findByTestId('panel')).textContent!);
const press = (name: string) => fireEvent.click(screen.getByRole('button', { name }));

it("each file keeps its own panel — open or closed, its width, its tab — and a remount (a reload) restores each; a new file starts at the defaults", async () => {
  toolStack = { panels: {}, collapsed: {} };
  stackWrites.length = 0;
  const kept = { state: {} };
  let page = tab(kept);
  expect(await panel()).toEqual({ open: true, width: 216, tab: null, detail: null });
  press('300'); press('layers'); press('toggle');
  expect(await panel()).toEqual({ open: false, width: 300, tab: 'layers', detail: null });
  // Another file: its own panel, at the defaults, not the first file's.
  await page.show(B);
  await screen.findByTestId('panel');
  expect(await panel()).toEqual({ open: true, width: 216, tab: null, detail: null });
  press('260');
  expect(await panel()).toEqual({ open: true, width: 260, tab: null, detail: null });
  // Each is in its own file's view, and nothing in the tab's settings.
  expect(Object.fromEntries(Object.entries((kept.state as any).renderers).map(([key, view]: any) => [JSON.parse(key)[0], view.panel])))
    .toEqual({ [A]: { open: false, width: 300, tab: 'layers' }, [B]: { width: 260 } });
  expect(stackWrites).toEqual([]);
  // A reload: each file comes back as it was left, even in a view too narrow to open a panel of its own accord.
  page.unmount();
  frameWidth = 800;
  page = tab(kept);
  expect(await panel()).toEqual({ open: false, width: 300, tab: 'layers', detail: null });
  await page.show(B);
  await screen.findByTestId('panel');
  expect(await panel()).toEqual({ open: false, width: 260, tab: null, detail: null });
  press('toggle');
  page.unmount();
  page = tab(kept);
  await page.show(B);
  await screen.findByTestId('panel');
  expect(await panel()).toEqual({ open: true, width: 260, tab: null, detail: null });
});

it("a file with no panel of its own starts from the tab's old shared one, which is then the file's and gone from the tab's settings", async () => {
  toolStack = { panels: { flat: { width: 280 }, flatDetail: { height: 200 }, tree: { width: 240 } }, collapsed: { flat: true, tree: true }, tabs: { board: 'nets', model: 'tree' } };
  stackWrites.length = 0;
  const kept = { state: {} };
  tab(kept);
  expect(await panel()).toEqual({ open: false, width: 280, tab: 'nets', detail: 200 });
  expect((kept.state as any).renderers[JSON.stringify([A, 'panelled'])].panel).toEqual({ open: false, width: 280, tab: 'nets', detailHeight: 200 });
  // The shared form is dropped, the other panels' sizes and folds kept.
  expect(toolStack).toEqual({ panels: { tree: { width: 240 } }, collapsed: { tree: true }, tabs: undefined });
});
