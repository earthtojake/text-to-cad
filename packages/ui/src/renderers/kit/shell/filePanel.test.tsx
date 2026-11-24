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
// The observers on the page, so a test can resize the view (`resize`).
const observers = new Set<() => void>();
const resize = (width: number) => act(() => { frameWidth = width; observers.forEach(callback => callback()); });
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    callback: () => void;
    constructor(callback: () => void) { this.callback = callback; }
    observe() { observers.add(this.callback); } unobserve() {} disconnect() { observers.delete(this.callback); }
  });
  Element.prototype.getBoundingClientRect = function (this: Element) {
    return this.hasAttribute('data-frame') ? DOMRect.fromRect({ x: 0, y: 0, width: frameWidth, height: 700 }) : rect.call(this);
  };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Element.prototype.getBoundingClientRect = rect; frameWidth = 1280; });

// The tab's settings as the renderer reads them, and what it writes back.
let toolStack: any = { panels: {}, collapsed: {} };
const stackWrites: any[] = [];
// A compact view (`appearance.compact`: a picture taken out of sight), as the frame tells the panel.
let compact = false;
function Panelled() {
  const frameRef = useRef<HTMLDivElement>(null);
  const flat = useFlatPanelState({ frameRef, compact, kind: 'board', toolStack,
    onToolStackChange: (patch: any) => { stackWrites.push(patch); toolStack = { ...toolStack, ...(typeof patch === 'function' ? patch(toolStack) : patch) }; } });
  // Open or closed is the person's choice the record keeps (`open`, absent for the default, open); where the panels
  // stand at a width is `sidebars.js`'s, never written (`sidebars.test.js`).
  return <div ref={frameRef} data-frame="">
    <output data-testid="panel">{JSON.stringify({ open: flat.record.open !== false, width: flat.width, tab: flat.tab ?? null })}</output>
    <button type="button" onClick={() => flat.change({ open: flat.record.open === false })}>toggle</button>
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
  let register: () => void = () => {};
  function Tab() {
    const [file, setFile] = useState(A);
    const [state, setState] = useState(kept.state);
    // The host's renderers, handed anew when it registers them again: the renderer mounts again on the same file.
    const [renderers, setRenderers] = useState(() => [renderer]);
    show = setFile;
    register = () => setRenderers([renderer]);
    kept.state = state;
    return <FileViewer file={file} host={host as any} renderers={renderers} state={state} onStateChange={next => { kept.state = next; setState(next); }} />;
  }
  const view = render(<Tab />);
  return { unmount: view.unmount, show: (file: string) => act(() => show(file)), register: () => act(() => register()) };
}
const panel = async () => JSON.parse((await screen.findByTestId('panel')).textContent!);
const press = (name: string) => fireEvent.click(screen.getByRole('button', { name }));

it("each file keeps its own panel — open or closed, its width, its tab — and a remount (a reload) restores each; a new file starts at the defaults", async () => {
  toolStack = { panels: {}, collapsed: {} };
  stackWrites.length = 0;
  const kept = { state: {} };
  let page = tab(kept);
  expect(await panel()).toEqual({ open: true, width: 232, tab: null });
  press('300'); press('layers'); press('toggle');
  expect(await panel()).toEqual({ open: false, width: 300, tab: 'layers' });
  // Another file: its own panel, at the defaults, not the first file's.
  await page.show(B);
  await screen.findByTestId('panel');
  expect(await panel()).toEqual({ open: true, width: 232, tab: null });
  press('260');
  expect(await panel()).toEqual({ open: true, width: 260, tab: null });
  // Each is in its own file's view, and nothing in the tab's settings.
  expect(Object.fromEntries(Object.entries((kept.state as any).renderers).map(([key, view]: any) => [JSON.parse(key)[0], view.panel])))
    .toEqual({ [A]: { open: false, width: 300, tab: 'layers' }, [B]: { width: 260 } });
  expect(stackWrites).toEqual([]);
  // A reload: each file comes back as it was left, in a narrow view too (the choice is kept, not the width's collapse).
  page.unmount();
  frameWidth = 800;
  page = tab(kept);
  expect(await panel()).toEqual({ open: false, width: 300, tab: 'layers' });
  await page.show(B);
  await screen.findByTestId('panel');
  expect(await panel()).toEqual({ open: true, width: 260, tab: null });
  press('toggle');
  page.unmount();
  page = tab(kept);
  await page.show(B);
  await screen.findByTestId('panel');
  expect(await panel()).toEqual({ open: false, width: 260, tab: null });
});

it("a file with no panel of its own starts from the tab's old shared one, which is then the file's and gone from the tab's settings", async () => {
  toolStack = { panels: { flat: { width: 280 }, tree: { width: 240 } }, collapsed: { flat: true, tree: true }, tabs: { board: 'nets', model: 'tree' } };
  stackWrites.length = 0;
  const kept = { state: {} };
  tab(kept);
  expect(await panel()).toEqual({ open: false, width: 280, tab: 'nets' });
  expect((kept.state as any).renderers[JSON.stringify([A, 'panelled'])].panel).toEqual({ open: false, width: 280, tab: 'nets' });
  // The shared form is dropped, the other panels' sizes and folds kept.
  expect(toolStack).toEqual({ panels: { tree: { width: 240 } }, collapsed: { tree: true }, tabs: undefined });
});

it("what the right panel it once had, and the \\ that once hid everything, kept is read as nothing", async () => {
  toolStack = { panels: {}, collapsed: {} };
  function Right() {
    const frameRef = useRef<HTMLDivElement>(null);
    const flat = useFlatPanelState({ frameRef, kind: 'board', toolStack, onToolStackChange: () => {} });
    return <div ref={frameRef} data-frame="">
      <output data-testid="record">{JSON.stringify(flat.record)}</output>
      <button type="button" onClick={() => flat.change({ open: false, right: false, rightWidth: 300, sections: { view: false }, hidden: true })}>choose</button>
    </div>;
  }
  const own = defineFileRenderer({ id: 'right', priority: 2, matches: () => true, prepare: async () => ({ data: null }), load: async () => ({ default: Right }) });
  const kept = { state: {} as any };
  const view = () => render(<FileViewer file={A} host={host as any} renderers={[own]} state={kept.state} onStateChange={next => { kept.state = next; }} />);
  let page = view();
  expect(JSON.parse((await screen.findByTestId('record')).textContent!)).toEqual({});
  press('choose');
  page.unmount();
  page = view();
  expect(JSON.parse((await screen.findByTestId('record')).textContent!)).toEqual({ open: false });
  page.unmount();
});

it("a compact view (a picture taken out of sight) leaves the tab's old shared panel for the file the person opens", async () => {
  const shared = { panels: { flat: { width: 280 } }, collapsed: { flat: true }, tabs: { board: 'nets' } };
  toolStack = shared;
  stackWrites.length = 0;
  compact = true;
  try {
    const kept = { state: {} };
    tab(kept);
    await screen.findByTestId('panel');
    expect(stackWrites).toEqual([]);
    expect(toolStack).toBe(shared);
  } finally {
    compact = false;
  }
});

// The panel's width is one number (`sidebars.js`): the default, whatever the view's width; only the grip is bounded,
// leaving the model 640px as it is dragged.
it("draws one width at every view width, its grip bounded by 200 and 480px whatever the view; a stored width past them reads as the bound", async () => {
  frameWidth = 1024;
  function Capped({ stored }: { stored?: number }) {
    const frameRef = useRef<HTMLDivElement>(null);
    const flat = useFlatPanelState({ frameRef, kind: 'board', toolStack: { panels: stored ? { flat: { width: stored } } : {}, collapsed: {} }, onToolStackChange: () => {} });
    return <div ref={frameRef} data-frame=""><output data-testid="width">{flat.width}</output><output data-testid="max">{flat.maxWidth}</output></div>;
  }
  const read = () => [screen.getByTestId('width').textContent, screen.getByTestId('max').textContent];
  const view = render(<Capped />);
  expect(read()).toEqual(['232', '480']);
  resize(700);
  expect(read()).toEqual(['232', '480']);
  resize(1440);
  expect(read()).toEqual(['232', '480']);
  view.unmount();
  render(<Capped stored={660} />);
  expect(read()).toEqual(['480', '480']);
});
