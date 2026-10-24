import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's surfaces a RENDERER fills — the viewport menu and Quick Edit — driven end to end
// through the real RendererShell and useRendererShell under the shell
// harness (a renderer that uses both), with only the WebGL viewport replaced. The stand-in
// hands the overlay the same viewport context the real one does (a host the pointer events arrive
// on, a runtime whose renderer's canvas is the scene's), and records the props the shell wired, so
// the camera reports reach the renderer through exactly the callbacks the real viewport calls.
// The viewport's own half of those reports (a resize, a preview camera) is ShellViewport.test.tsx.
// `props`: the editor's viewport; `preview`: Preview's, a viewport of its own while it is open.
// `gpu`, where a test sets it: what the viewport says of its WebGL renderer (`softwareRendering`),
// and the Render scenes it was asked to prepare ahead.
const viewport = vi.hoisted(() => ({ props: null as any, preview: null as any, annotationAt: null as null | ((x: number, y: number) => string | null),
  gpu: null as null | { software: boolean; prepared: number } }));
vi.mock('../../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    if (props.preview) viewport.preview = props; else viewport.props = props;
    useEffect(() => () => { if (props.preview) viewport.preview = null; }, []);
    useImperativeHandle(ref, () => ({
      captureScreenshotBlob: async () => new Blob(['pixels'], { type: 'image/png' }),
      annotationAt: (x: number, y: number) => viewport.annotationAt?.(x, y) ?? null,
      promptCamera: () => ({ camera: { position: [0, -100, 0], target: [0, 0, 0], up: [0, 0, 1], orthographicHalfHeight: 40 }, width: 800, height: 600 }),
      ...(viewport.gpu ? {
        softwareRendering: () => viewport.gpu!.software,
        prepareViewSettings: async (scene: any) => { if (scene.render.enabled) viewport.gpu!.prepared += 1; },
      } : {}),
    }));
    const hostRef = useRef<HTMLDivElement | null>(null);
    const runtimeRef = useRef<any>(null);
    const context = { hostRef, runtimeRef, mountRef: hostRef, viewerReadyTick: 1, commitScene: () => true };
    return <div ref={hostRef} data-stand-in-viewport="">
      <canvas ref={canvas => { runtimeRef.current = canvas ? { renderer: { domElement: canvas } } : null; }} />
      {typeof props.children === 'function' ? props.children(context) : props.children}
    </div>;
  })
}));
import HarnessRenderer from '../../../../dist/renderers/shell-harness/HarnessRenderer.js';
import { ViewerElementContext, ViewerHostContext } from '../../../../dist/host/context.js';
import { testHost } from '../../../../dist/host/testing/host.js';
import { createAnimationClock } from '../../../../dist/renderers/kit/tools/playbar/animationClock.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewport.props = null; viewport.preview = null; });


function mount(host = testHost(), state?: unknown, name = 'one.harness', element: { current: HTMLElement | null } | null = null) {
  const save = vi.fn();
  const navigation = vi.fn();
  let settings: any = { toolStack: { panels: {}, collapsed: {} } };
  const listeners = new Set<() => void>();
  const preferences = { getSnapshot: () => settings, subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    update: (patch: any) => { settings = { ...settings, ...patch }; listeners.forEach(listener => listener()); } };
  const props = { source: { id: 'one' }, file: { path: `/models/${name}`, name, kind: 'file' }, document: null,
    onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' },
    state, onStateChange: save, onNavigationActionsChange: navigation, reload() {}, data: { services: { preferences } } };
  // `element`: the viewer the keyboard reaches (its Escape and Delete), as a file viewer provides.
  const view = render(<ViewerHostContext.Provider value={host}><ViewerElementContext.Provider value={element as any}>
    <HarnessRenderer {...(props as any)} />
  </ViewerElementContext.Provider></ViewerHostContext.Provider>);
  const canvas = view.container.querySelector('[data-stand-in-viewport] > canvas') as HTMLCanvasElement;
  const overlay = (name: string) => view.container.querySelector(`[data-harness-${name}]`)!.textContent;
  return { ...view, canvas, overlay, save, navigation };
}

// A secondary press as the browser delivers one: down, (moves), up, all on the canvas.
function pointer(target: Element, type: string, init: Record<string, unknown>) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.assign(event, { pointerId: 1, pointerType: 'mouse', buttons: 0, shiftKey: false, ...init });
  act(() => { target.dispatchEvent(event); });
}
function secondaryTap(target: Element, x: number, y: number, init: Record<string, unknown> = {}) {
  pointer(target, 'pointerdown', { button: 2, buttons: 2, clientX: x, clientY: y, ...init });
  pointer(target, 'pointerup', { button: 2, clientX: x, clientY: y, ...init });
}
const menuAnchor = () => document.querySelector('button[aria-hidden="true"][style*="position: fixed"]') as HTMLElement | null;
// The harness's selection: a press it notes through its menu, which Quick Edit carries as a reference.
function pick(canvas: Element) {
  secondaryTap(canvas, 300, 200);
  act(() => { fireEvent.click(screen.getByRole('menuitem', { name: 'Note the press' })); });
}

it('a secondary tap on the canvas opens the renderer\'s own items at the press, in the renderer\'s state, and an item acts on that press', () => {
  const { canvas, overlay } = mount();
  secondaryTap(canvas, 300, 200);
  const menu = screen.getByRole('menu');
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Note the press', 'Clear the note']);
  // It opens AT the press: the anchor is the press point, not a corner.
  expect([menuAnchor()?.style.left, menuAnchor()?.style.top]).toEqual(['300px', '200px']);
  // The second item is disabled until the first has been taken: the renderer's state reaching the menu.
  expect(screen.getByRole('menuitem', { name: 'Clear the note' }).hasAttribute('data-disabled')).toBe(true);
  fireEvent.keyDown(menu, { key: 'Escape' });
  expect(screen.queryByRole('menu')).toBeNull();
  // A second press elsewhere opens it there instead.
  secondaryTap(canvas, 520, 60);
  expect([menuAnchor()?.style.left, menuAnchor()?.style.top]).toEqual(['520px', '60px']);
  act(() => { fireEvent.click(screen.getByRole('menuitem', { name: 'Note the press' })); });
  expect(screen.queryByRole('menu')).toBeNull();
  expect(overlay('menu-note')).toBe('520,60');
  secondaryTap(canvas, 520, 60);
  expect(screen.getByRole('menuitem', { name: 'Clear the note' }).hasAttribute('data-disabled')).toBe(false);
});

it('a press the renderer has nothing to say about, a secondary drag, or a press off the canvas opens no menu', () => {
  const { canvas, container } = mount();
  // Shift: the harness answers null, which is "nothing to offer here".
  secondaryTap(canvas, 300, 200, { shiftKey: true });
  expect(screen.queryByRole('menu')).toBeNull();
  // A secondary DRAG is the camera's (a pan), past the tap slop.
  pointer(canvas, 'pointerdown', { button: 2, buttons: 2, clientX: 300, clientY: 200 });
  pointer(canvas, 'pointermove', { buttons: 2, clientX: 390, clientY: 240 });
  pointer(canvas, 'pointerup', { button: 2, clientX: 390, clientY: 240 });
  expect(screen.queryByRole('menu')).toBeNull();
  // A control drawn over the canvas keeps its own presses.
  secondaryTap(container.querySelector('[data-harness-overlay]')!, 300, 200);
  expect(screen.queryByRole('menu')).toBeNull();
  // And a plain tap still opens it: the gesture above was the only difference.
  secondaryTap(canvas, 300, 200);
  expect(screen.getByRole('menu')).toBeTruthy();
});

it('Quick Edit is there once something is picked, with what the host can do, is put away in Preview, and nothing sits at the bottom', async () => {
  const destination = { kind: 'composer', available: true } as const;
  const send = vi.fn(async () => ({ status: 'sent' as const, partIds: [] }));
  const { container, canvas } = mount(testHost({ promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async () => ({ status: 'added', partIds: [] }), send } }));
  expect(container.querySelector('[data-viewport-bottom-actions]')).toBeNull();
  // Nothing picked, nothing drawn: no Quick Edit at all, not even a button.
  expect(container.querySelector('[data-quick-edit-box]')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Quick Edit' })).toBeNull();
  pick(canvas);
  const box = screen.getByRole('region', { name: 'Quick Edit' });
  expect(box.querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('1 ref');
  expect(within(box).getAllByRole('button').map(button => button.getAttribute('aria-label') || button.textContent)).toEqual(['Close Quick Edit', 'Copy Prompt', 'Queue', 'Send']);
  // Its X clears the pick, as a press on the background would, and goes with it.
  fireEvent.click(within(box).getByRole('button', { name: 'Close Quick Edit' }));
  expect(screen.queryByRole('region', { name: 'Quick Edit' })).toBeNull();
  pick(canvas);
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  await waitFor(() => expect(container.querySelector('[data-preview-chrome]')!.hasAttribute('inert')).toBe(true));
  expect(container.querySelector('[data-preview-chrome]')!.contains(container.querySelector('[data-quick-edit]'))).toBe(true);
});

// A stroke as the drawing tools put one into the model.
const ink = (id: string) => ({ id, kind: 'stroke', points: new Float32Array([0, 0, 0, 1, 0, 0]), color: '#ff2d55', width: 2, touches: [] });

it("an annotation opens Quick Edit, which sends the note with the files made of its view and its annotation, and goes with them", async () => {
  const destination = { kind: 'composer', available: true } as const;
  const send = vi.fn(async (_context: unknown) => ({ status: 'sent' as const, partIds: [] }));
  const promptFiles = {
    create: vi.fn(async (_request: any) => ({ snapshot: '/tmp/p/one-1.snapshot.json' })),
    read: vi.fn(async () => new Blob(['{}'], { type: 'application/json' })),
  };
  const host = testHost({ promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async () => ({ status: 'added', partIds: [] }), send } as any, promptFiles });
  mount(host);
  fireEvent.click(screen.getByRole('button', { name: 'Pencil' }));
  act(() => viewport.props.annotation.add([ink('a')]));
  const box = screen.getByRole('region', { name: 'Quick Edit' });
  expect(box.querySelector('[data-quick-edit-ref="annotation"]')).not.toBeNull();
  const note = within(box).getByRole('textbox', { name: 'Describe your changes' });
  expect(document.activeElement).toBe(note);
  note.textContent = 'Add a boss here.';
  fireEvent.input(note);
  expect(promptFiles.create).not.toHaveBeenCalled();
  fireEvent.keyDown(note, { key: 'Enter' });
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  // The view on screen, as a snapshot job says it (its mode and Grid switch with it, so the snapshot
  // replays it), with the annotation in the same snapshot file.
  const [request] = promptFiles.create.mock.calls[0] as any[];
  expect(request).toMatchObject({ name: 'one.harness', input: '/models/one.harness', annotation: { units: 'mm', marks: [{ id: 'a', kind: 'stroke' }] } });
  expect(request.views).toEqual([{ label: 'current view', camera: { position: [0, -100, 0], target: [0, 0, 0], up: [0, 0, 1], orthographicHalfHeight: 40 },
    display: { mode: 'solid', grid: false }, width: 1600, height: 1200 }]);
  const context = send.mock.calls[0][0] as any;
  expect(context.parts.map((part: any) => [part.kind, part.label ?? part.id])).toEqual([['text', 'text'], ['reference', 'file'],
    ['attachment', 'Snapshot (cadgen snapshot --annotation)']]);
  expect(await context.parts[2].path).toBe('/tmp/p/one-1.snapshot.json');
  expect(context.parts.filter((part: any) => part.kind === 'attachment').map((part: any) => part.mimeType)).toEqual(['application/json']);
  expect(promptFiles.read).not.toHaveBeenCalled();
  // Sent, the note goes with its annotation.
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Quick Edit' })).toBeNull());
  expect(viewport.props.annotation.hasAnnotation).toBe(false);
});

it('a clipboard destination has no snapshot in the navbar; the annotation is Quick Edit\'s chip, its pen first', async () => {
  const destination = { kind: 'clipboard', available: true } as const;
  const writeImage = vi.fn(async () => {}), deliver = vi.fn();
  const { navigation } = mount(testHost({
    promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver } as any,
    clipboard: { writeText: async () => {}, writeImage },
  }));
  expect(navigation.mock.calls.flatMap(([actions]) => actions)).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: 'Pencil' }));
  act(() => viewport.props.annotation.add([ink('a')]));
  const chip = screen.getByRole('region', { name: 'Quick Edit' }).querySelector('[data-quick-edit-ref="annotation"]')!;
  expect(chip.querySelector('svg[data-pick-glyph="pencil"]')).not.toBeNull();
  // A clipboard destination's Quick Edit copies its prompt, and nothing else.
  expect(within(screen.getByRole('region', { name: 'Quick Edit' })).queryByRole('button', { name: 'Queue' })).toBeNull();
  expect(deliver).not.toHaveBeenCalled();
});

it("under Select a press on the annotation picks its mark before anything under it; Shift adds, Escape lets go, Delete deletes", () => {
  // A file with Select (`panel*`): ink 'a' lies at x < 100 on the canvas, ink 'b' at x >= 100 and y < 50.
  viewport.annotationAt = (x: number, y: number) => (x < 100 ? 'a' : y < 50 ? 'b' : null);
  const { canvas } = mount(testHost(), undefined, 'panel-one.harness', { current: document.body });
  act(() => viewport.props.annotation.add([ink('a'), ink('b'), ink('c')]));
  const press = (x: number, y: number, shiftKey = false) => fireEvent.pointerDown(canvas, { button: 0, clientX: x, clientY: y, shiftKey, pointerId: 1 });
  const selected = () => viewport.props.annotation.selected;
  press(10, 10);
  expect(selected()).toEqual(['a']);
  press(150, 10, true);
  expect(selected()).toEqual(['a', 'b']);
  press(150, 10, true);
  expect(selected()).toEqual(['a']);
  // A press on no ink lets go of it, unless Shift keeps it.
  press(150, 150, true);
  expect(selected()).toEqual(['a']);
  press(150, 150);
  expect(selected()).toEqual([]);
  press(10, 10);
  fireEvent.keyDown(canvas, { key: 'Escape' });
  expect(selected()).toEqual([]);
  // With nothing picked Delete deletes nothing; with 'a' picked, 'a' alone.
  fireEvent.keyDown(canvas, { key: 'Delete' });
  expect(viewport.props.annotation.items.map((item: any) => item.id)).toEqual(['a', 'b', 'c']);
  press(10, 10);
  fireEvent.keyDown(canvas, { key: 'Delete' });
  expect(viewport.props.annotation.items.map((item: any) => item.id)).toEqual(['b', 'c']);
  viewport.annotationAt = null;
});

it("Pencil and Shapes are two plain tools on the strip; one row under the strip is theirs both: the tools of the one that is up, then Color, Stroke width, Placement and Clear, disabled with nothing to do", async () => {
  mount(testHost(), undefined, 'panel-one.harness');
  const strip = within(screen.getByRole('group', { name: 'Interaction tools' }));
  expect(strip.queryByRole('button', { name: 'Annotate' })).toBeNull();
  // No chevron, no menu: a button each.
  expect(strip.getAllByRole('button').map(button => button.getAttribute('aria-label')).slice(0, 4)).toEqual(['Select', 'Pencil', 'Shapes', 'Keep']);
  expect(strip.getByRole('button', { name: 'Pencil' }).querySelector('svg')!.getAttribute('class')).toContain('lucide-pencil');
  expect(strip.getByRole('button', { name: 'Shapes' }).querySelector('svg')!.getAttribute('class')).toContain('lucide-square');
  expect(screen.queryByRole('toolbar', { name: 'Annotation controls' })).toBeNull();
  fireEvent.click(strip.getByRole('button', { name: 'Pencil' }));
  expect([viewport.props.annotation.tool, strip.getByRole('button', { name: 'Pencil' }).getAttribute('aria-pressed')]).toEqual(['freedraw', 'true']);
  // Not a panel of the tool stack: a toolbar of its own, hung under the strip.
  const row = screen.getByRole('toolbar', { name: 'Annotation controls' });
  expect([row.closest('[data-cad-tool-stack]'), row.closest('[data-tool-panel]')]).toEqual([null, null]);
  const panel = () => within(screen.getByRole('toolbar', { name: 'Annotation controls' }));
  expect(panel().getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Pen', 'Highlighter', 'Eraser', 'Color', 'Stroke width', 'Placement', 'Clear annotations']);
  const clear = () => panel().getByRole('button', { name: 'Clear annotations' }).hasAttribute('disabled');
  expect(clear()).toBe(true);
  // Ink enables Clear. Undo and Redo are the keyboard's, ⌘Z and ⇧⌘Z (below), with no buttons.
  act(() => viewport.props.annotation.add([ink('a')]));
  expect(clear()).toBe(false);
  // Shapes' row starts with its own tools.
  fireEvent.click(strip.getByRole('button', { name: 'Shapes' }));
  expect(panel().getAllByRole('button').slice(0, 5).map(button => button.getAttribute('aria-label'))).toEqual(['Rectangle', 'Line', 'Arrow', 'Ellipse', 'Text']);
});

it("choosing the Highlighter in Pencil's row makes the strip's Pencil show it, and a press on Pencil takes up what it last drew with; Shapes opens on the Rectangle; switching shows each kind's own colour, weight and placement", async () => {
  mount(testHost(), undefined, 'panel-one.harness');
  const strip = within(screen.getByRole('group', { name: 'Interaction tools' }));
  const icon = (name: string) => strip.getByRole('button', { name }).querySelector('svg')!.getAttribute('class') ?? '';
  const row = () => within(screen.getByRole('toolbar', { name: 'Annotation controls' }));
  fireEvent.click(strip.getByRole('button', { name: 'Pencil' }));
  fireEvent.click(row().getByRole('button', { name: 'Highlighter' }));
  expect(viewport.props.annotation.tool).toBe('highlighter');
  expect(row().getByRole('button', { name: 'Highlighter' }).getAttribute('aria-pressed')).toBe('true');
  expect(icon('Pencil')).toContain('lucide-highlighter');
  // The highlighter's own settings, set while it is up: yellow to start.
  expect(viewport.props.annotation.style).toEqual({ color: '#ffe600', strokeWidth: 2, placement: 'surface' });
  act(() => { viewport.props.annotation.selectColor('#39ff14'); viewport.props.annotation.selectStrokeWidth(4); viewport.props.annotation.selectPlacement('plane'); });
  // Shapes takes up the Rectangle; Pencil keeps the Highlighter.
  fireEvent.click(strip.getByRole('button', { name: 'Shapes' }));
  expect(viewport.props.annotation.tool).toBe('rectangle');
  expect(strip.getByRole('button', { name: 'Pencil' }).getAttribute('aria-pressed')).toBe('false');
  expect(icon('Pencil')).toContain('lucide-highlighter');
  expect(viewport.props.annotation.style).toEqual({ color: '#ff2d55', strokeWidth: 2, placement: 'surface' });
  fireEvent.click(row().getByRole('button', { name: 'Rectangle' }));
  expect(icon('Shapes')).toContain('lucide-square');
  fireEvent.click(strip.getByRole('button', { name: 'Pencil' }));
  expect(viewport.props.annotation).toMatchObject({ tool: 'highlighter', style: { color: '#39ff14', strokeWidth: 4, placement: 'plane' } });
  fireEvent.click(strip.getByRole('button', { name: 'Shapes' }));
  expect(viewport.props.annotation.tool).toBe('rectangle');
});

it('⌘Z and ⇧⌘Z walk the annotation\'s history from anywhere in the viewer; a text field keeps its own', () => {
  const { canvas } = mount(testHost(), undefined, 'panel-one.harness', { current: document.body });
  act(() => viewport.props.annotation.add([ink('a')]));
  act(() => viewport.props.annotation.add([ink('b')]));
  const ids = () => viewport.props.annotation.items.map((item: any) => item.id);
  fireEvent.keyDown(canvas, { key: 'z', metaKey: true });
  expect(ids()).toEqual(['a']);
  const field = document.createElement('input');
  document.body.append(field);
  fireEvent.keyDown(field, { key: 'z', metaKey: true });
  expect(ids()).toEqual(['a']);
  field.remove();
  fireEvent.keyDown(canvas, { key: 'z', metaKey: true, shiftKey: true });
  expect(ids()).toEqual(['a', 'b']);
});

it('under Select the pointer resting on a mark lights it, and the part under it hears nothing', () => {
  viewport.annotationAt = (x: number) => (x < 100 ? 'a' : null);
  const { canvas } = mount(testHost(), undefined, 'panel-one.harness');
  act(() => viewport.props.annotation.add([ink('a'), ink('b')]));
  const heard = vi.fn();
  canvas.addEventListener('pointermove', heard);
  const move = (x: number, buttons = 0) => fireEvent.pointerMove(canvas, { clientX: x, clientY: 10, buttons, pointerId: 1 });
  move(10);
  expect(viewport.props.hoveredAnnotation).toEqual(['a']);
  expect(heard).not.toHaveBeenCalled();
  const frame = canvas.closest('[data-slot="cad-file-view"]')!;
  expect(frame.classList.contains('cursor-pointer')).toBe(true);
  // Off the ink the part hears the pointer again; a drag lights nothing.
  move(150);
  expect(viewport.props.hoveredAnnotation).toBeNull();
  expect(heard).toHaveBeenCalledTimes(1);
  expect(frame.classList.contains('cursor-pointer')).toBe(false);
  move(10, 1);
  expect(viewport.props.hoveredAnnotation).toBeNull();
  move(10);
  fireEvent.pointerLeave(canvas.closest('[data-slot="cad-file-view"]')!);
  expect(viewport.props.hoveredAnnotation).toBeNull();
  viewport.annotationAt = null;
});

it('a host with no prompt workflow gets no snapshot, and Quick Edit copies a prompt: left out, not disabled', () => {
  // The test host composes `unavailablePromptContext`.
  const { navigation, canvas } = mount();
  expect(navigation.mock.calls.flatMap(([actions]) => actions)).toEqual([]);
  pick(canvas);
  expect(within(screen.getByRole('region', { name: 'Quick Edit' })).getAllByRole('button').map(button => button.getAttribute('aria-label') || button.textContent))
    .toEqual(['Close Quick Edit', 'Copy Prompt']);
});

it('the renderer is told the camera settled, through what the viewport reports: a recorded move and its own settle', async () => {
  const { overlay } = mount();
  expect(overlay('camera-settles')).toBe('0');
  // A camera that moved and was recorded (`onPerspectiveChange`) is a settle.
  act(() => { viewport.props.onPerspectiveChange({ position: [1, 2, 3], target: [0, 0, 0], up: [0, 0, 1], zoom: 1, projection: 'orthographic' }); });
  expect(overlay('camera-settles')).toBe('1');
  // So is the viewport's own settle (a preview camera, a resize), which records nothing.
  act(() => { viewport.props.onCameraSettled(); });
  expect(overlay('camera-settles')).toBe('2');
  // Preview's own view keeps no camera (it records no perspective), and the renderer still hears
  // its camera settle.
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  await waitFor(() => expect(viewport.preview).not.toBeNull());
  expect(viewport.preview.onPerspectiveChange ?? null).toBeNull();
  act(() => { viewport.preview.onCameraSettled(); });
  expect(overlay('camera-settles')).toBe('3');
});

it('a view that has gone writes nothing more: its last write is the one it makes as it unmounts, and a camera report after it writes no view again', () => {
  vi.useFakeTimers();
  try {
    const { save, unmount } = mount();
    const camera = (x: number) => ({ position: [x, 2, 3], target: [0, 0, 0], up: [0, 0, 1], zoom: 1, projection: 'orthographic' });
    act(() => { viewport.props.onPerspectiveChange(camera(1)); });
    const report = viewport.props.onPerspectiveChange;
    unmount();
    const last = save.mock.calls.at(-1)![0];
    expect(last.camera.position).toEqual([1, 2, 3]);
    // A report that lands after the file has gone (its runtime winding down) is not a write: a host
    // that dropped the view of the file it left must not see it come back.
    const writes = save.mock.calls.length;
    act(() => { report(camera(9)); vi.advanceTimersByTime(1000); });
    expect(save.mock.calls.length).toBe(writes);
  } finally {
    vi.useRealTimers();
  }
});

// The full reset crosses the renderer callback and the shell's tool/preview
// lifecycle; it must reach the camera only after those changes commit.

// A stand-in routine runtime: it says what was asked of it.
function routineRuntime(name: string, calls: string[]) {
  return { clips: [{ id: name }], clock: createAnimationClock(), onRelease: () => calls.push(`release ${name}`),
    onPlayToggle: () => calls.push(`play ${name}`) };
}

function mountRoutine(data: Record<string, unknown>, state: unknown = undefined) {
  const settings = { toolStack: { panels: {}, collapsed: {} } };
  const preferences = { getSnapshot: () => settings, subscribe: () => () => {}, update() {} };
  const props = (extra: Record<string, unknown>) => ({ source: { id: 'one' }, file: { path: '/models/one.harness', name: 'one.harness', kind: 'file' },
    document: null, onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, state,
    onStateChange() {}, onNavigationActionsChange() {}, reload() {}, data: { services: { preferences }, ...extra } });
  const view = render(<ViewerHostContext.Provider value={testHost()}><HarnessRenderer {...(props(data) as any)} /></ViewerHostContext.Provider>);
  return (extra: Record<string, unknown>) => view.rerender(
    <ViewerHostContext.Provider value={testHost()}><HarnessRenderer {...(props(extra) as any)} /></ViewerHostContext.Provider>);
}

it('opening another file while Preview is up leaves it; crossing touches neither the tools view\'s routine nor Preview\'s', async () => {
  const calls: string[] = [];
  const rerender = mountRoutine({ animation: routineRuntime('tools-a', calls), previewAnimation: routineRuntime('preview-a', calls), modelKey: 'a.glb' });
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  await screen.findByRole('button', { name: 'Exit preview' });
  // With Autoplay off, entering plays nothing and puts nothing down.
  expect(calls).toEqual([]);
  rerender({ animation: routineRuntime('tools-b', calls), previewAnimation: routineRuntime('preview-b', calls), modelKey: 'b.glb' });
  expect(screen.queryAllByRole('button', { name: 'Exit preview' })).toEqual([]);
  expect([calls, viewport.preview]).toEqual([[], null]);
});

it("under Autoplay Preview plays its own routine as it opens; the tools view's is not touched", async () => {
  const calls: string[] = [];
  mountRoutine({ animation: routineRuntime('tools', calls), previewAnimation: routineRuntime('preview', calls) },
    { version: 2, playback: { orbitSpeed: 1, autoplay: true } });
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  await screen.findByRole('button', { name: 'Exit preview' });
  await waitFor(() => expect(calls).toEqual(['play preview']));
  fireEvent.click(screen.getByRole('button', { name: 'Exit preview' }));
  expect(calls).toEqual(['play preview']);
});

it('a view that stops offering Preview while it is up leaves it as every exit does: its view goes, and nothing else', async () => {
  const calls: string[] = [];
  const tools = routineRuntime('tools', calls), preview = routineRuntime('preview', calls);
  const rerender = mountRoutine({ animation: tools, previewAnimation: preview });
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  await screen.findByRole('button', { name: 'Exit preview' });
  rerender({ animation: tools, previewAnimation: preview, previewable: false });
  expect([calls, viewport.preview, viewport.props.suspended]).toEqual([[], null, false]);
  expect(screen.queryAllByRole('button', { name: 'Exit preview' })).toEqual([]);
});

it.each([['a GPU', false, 1], ['a software renderer', true, 0]])('on %s, Preview is prepared ahead a moment after the model is on screen, or only as it is entered', (_name, software, prepared) => {
  // A software renderer (SwiftShader, llvmpipe) compiles for seconds on the page's one thread:
  // there Preview prepares as it is entered, under its cover, and nothing is asked of it before.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  try {
    viewport.gpu = { software: software as boolean, prepared: 0 };
    mount();
    act(() => { vi.advanceTimersByTime(599); });
    expect(viewport.gpu.prepared).toBe(0);
    act(() => { vi.advanceTimersByTime(1); });
    expect(viewport.gpu.prepared).toBe(prepared);
  } finally {
    vi.useRealTimers();
    viewport.gpu = null;
  }
});


it('text-only Quick Edit captures the current view at Copy without any annotations', async () => {
  const promptFiles = { create: vi.fn(async (_request: any) => ({ inline: '{"jobs":[]}' })), read: vi.fn() };
  let copied = '';
  const { canvas } = mount(testHost({ promptFiles, clipboard: {
    writeText: async text => { copied = await text; }, readText: async () => '', writeImage: async () => {} } }));
  pick(canvas);
  const note = screen.getByRole('textbox', { name: 'Describe your changes' });
  note.textContent = 'Keep this view.';
  fireEvent.input(note);
  // The harness's synthetic press reference is not a CAD selector. Clear it while the note stays.
  secondaryTap(canvas, 300, 200);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Clear the note' }));
  expect(promptFiles.create).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(copied).toContain('Snapshot JSON (cadgen snapshot --annotation):'));
  expect(promptFiles.create.mock.calls[0][0]).toMatchObject({ annotation: null,
    views: [{ label: 'current view', camera: { position: [0, -100, 0] } }] });
});
