import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ViewFrame from '../../../../dist/renderers/kit/shell/ViewFrame.js';
import { HOVER_TIP_DELAY_MS } from '../../../../dist/renderers/kit/shell/HoverTip.js';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any;
afterEach(cleanup);

// The update status is the frame's, one rule in every view, 2D or 3D (`docs/viewer-ux.md`, "Loading and status screens"): under the strip,
// at the top centre where there is no strip (a load, a compact host, Preview), and none while the card
// says why the chrome is gone; its Retry wherever the update offers one.
it('the update status stands under the strip, at the top centre without one, and gives way to the card of a view whose chrome is gone', () => {
  const failing = { pending: false, error: 'the GPU went away' };
  const status = { update: failing, onRetry: () => {} };
  const frame = (props: object) => render(<ViewFrame file="part.step" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}}
    onLayoutChange={() => {}} status={status} {...props}>{null}</ViewFrame>);
  const where = (view: ReturnType<typeof render>) => {
    const node = view.container.querySelector('[data-viewport-status]');
    if (!node) return 'none';
    return [node.closest('[data-cad-top-controls]') ? 'under the strip' : 'top centre', Boolean(node.querySelector('button[aria-label="Retry view update"]'))];
  };
  expect(where(frame({}))).toEqual(['under the strip', true]);
  cleanup();
  expect(where(frame({ compact: true }))).toEqual(['top centre', true]);
  cleanup();
  expect(where(frame({ chromeHidden: true }))).toEqual(['top centre', true]);
  cleanup();
  expect(where(frame({ chromeHidden: true, alert: { alert: { severity: 'error', title: 'Could not open', message: 'no' }, hasContent: false } }))).toBe('none');
  cleanup();
  // A view with nothing to say draws no status, wherever it would stand.
  const idle = render(<ViewFrame file="part.step" mobile={false} compact chromeHidden={false} tools={[]} layout={{}} onLayoutChange={() => {}}
    status={{ update: null }}>{null}</ViewFrame>);
  expect(idle.container.querySelector('[data-view-update-status]')).toBeNull();
});

// What a press would pick is the frame's in every view (`docs/viewer-ux.md`, "Tooltips and feedback"): the hover tip over the canvas, from
// the view's description of a pick (`inspect`); the panel is the lists alone, nothing of the pick under them.
it('the frame names what a press would pick in a tip beside the pointer, under Select and while no button is held, and draws no pane of the pick', () => {
  vi.useFakeTimers();
  const item = { id: 'selected:#U3', pick: '#U3', kind: 'solid', title: 'U3', tip: 'ATmega328P', facts: [{ label: 'Value', value: 'ATmega328P' }] };
  const inspect = { describe: () => item, hovered: '#U3' };
  const panel = { kind: 'test', label: 'Panel', searchLabel: 'Search', tabs: [{ id: 'list', label: 'List', content: <p>rows</p> }] };
  const frame = (props: object) => render(<ViewFrame file="board.kicad_pcb" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}}
    onLayoutChange={() => {}} selecting panel={panel} inspect={inspect} {...props}><canvas data-testid="canvas" /></ViewFrame>);
  const view = frame({});
  expect([view.container.querySelector('[data-flat-panel]') !== null, view.container.querySelector('[data-detail-head]')]).toEqual([true, null]);
  const canvas = view.getByTestId('canvas');
  fireEvent.pointerMove(canvas, { clientX: 40, clientY: 60, buttons: 0 });
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS); });
  expect(view.getByRole('tooltip').textContent).toBe('U3 · ATmega328P');
  // A drag puts it away; another tool than Select shows none.
  fireEvent.pointerMove(canvas, { clientX: 50, clientY: 60, buttons: 1 });
  expect(view.queryByRole('tooltip')).toBeNull();
  cleanup();
  const other = frame({ selecting: false });
  fireEvent.pointerMove(other.getByTestId('canvas'), { clientX: 40, clientY: 60, buttons: 0 });
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS); });
  expect(other.queryByRole('tooltip')).toBeNull();
  vi.useRealTimers();
});

it("the hover tip takes the view's short words where it has them, and never runs the full description for a hover", () => {
  vi.useFakeTimers();
  const describe = vi.fn(() => null);
  const inspect = { describe, tip: (id: string) => `${id} · hinge`, hovered: 'pin' };
  const view = render(<ViewFrame file="part.step" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}} onLayoutChange={() => {}}
    selecting inspect={inspect}><canvas data-testid="canvas" /></ViewFrame>);
  fireEvent.pointerMove(view.getByTestId('canvas'), { clientX: 10, clientY: 10, buttons: 0 });
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS); });
  expect(view.getByRole('tooltip').textContent).toBe('pin · hinge');
  expect(describe).not.toHaveBeenCalled();
  vi.useRealTimers();
});


// What belongs to the picture is in the picture's scheme, whatever the app's theme (`docs/design-system.md`, "The viewport's
// scheme"): the page's loading cover (`file-viewer/presentation`'s, before any view is up), the view's, Preview's (on
// Preview's own backdrop, where its Background is set), the update status and the alert card. Each one's scheme is the
// class over it, which sets its canvas and its ink.
it("the loading covers, Preview's, the update status and the alert card are in the viewport's scheme, never the app's", async () => {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  const { ViewerLoadingOverlay } = await import('../../../../dist/file-viewer/presentation.js');
  const { usePreviewFrame } = await import('../../../../dist/renderers/kit/shell/usePreviewFrame.js');
  const schemeOf = (node: Element | null) => node?.closest('.light, .dark')?.classList.contains('light') ? 'light' : node ? 'dark' : null;
  // Preview's cover, as the frame draws it the moment Preview is entered: on Preview's backdrop (`background`, its
  // Background setting, off by default) over a view whose viewport is `scheme`.
  const Preview = ({ scheme, background }: { scheme: string; background: object }) => usePreviewFrame({ previewing: true, setPreviewing() {},
    modelKey: 'part.step', fileView: { file: { name: 'part.step' } }, hostElement: null, stageColor: scheme === 'dark' ? '#1f1f1f' : '#f5f5f5',
    viewportScheme: scheme, View: () => null, view: null, desired: { view: { background } }, sceneScaleMode: 'cad', viewRef: { current: null },
    moving: false, orbit: false, onOrbitChange() {}, orbitSpeed: 1, onOrbitSpeedChange() {}, render: null, disabled: false, mobile: false }).frame.overlays;
  // A dark app over a Light Background, and a light app over a Dark one: each cover, the status and the card take the
  // viewport's, whatever the app's.
  for (const [app, background] of [['dark', 'light'], ['light', 'dark']]) {
    const page = render(<div className={app}><ViewerLoadingOverlay viewerLoading background={background} /></div>);
    const view = render(<div className={app}><ViewFrame file="part.step" mobile={false} compact={false} chromeHidden tools={[]} layout={{}} onLayoutChange={() => {}}
      viewport={{ scheme: background }} loading={{ opening: true }} status={{ update: { pending: false, error: 'the GPU went away' } }}>{null}</ViewFrame></div>);
    const alerted = render(<div className={app}><ViewFrame file="part.step" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}} onLayoutChange={() => {}}
      viewport={{ scheme: background }} status={{ update: { pending: false, error: 'the GPU went away' } }}
      alert={{ alert: { severity: 'warning', title: 'Some parts are missing', message: 'two' }, hasContent: true }}>{null}</ViewFrame></div>);
    const preview = render(<div className={app}><Preview scheme={background} background={{ enabled: false, color: '#ffffff', opacity: 1 }} /></div>);
    expect([schemeOf(page.container.querySelector('.cad-loading-overlay')), schemeOf(view.container.querySelector('.cad-loading-overlay')),
      schemeOf(view.container.querySelector('[data-viewport-status]')), schemeOf(alerted.container.querySelector('[data-viewport-status]')),
      schemeOf(alerted.container.querySelector('[role="alert"]')), schemeOf(preview.container.querySelector('[data-preview-cover] [data-loading-step]'))])
      .toEqual([background, background, background, background, background, background]);
    // The one indicator: a step line over a progress bar, and no mark.
    const indicator = view.container.querySelector('[data-viewer-loading]')!;
    expect([indicator.querySelector('[data-loading-step]')?.textContent, Boolean(indicator.querySelector('[role="progressbar"]')),
      indicator.querySelectorAll('img, picture, svg').length]).toEqual(['Preparing view', true, 0]);
    cleanup();
  }
  // Preview's Background set: its cover is that colour, in its ink, whatever the viewport's and the app's.
  for (const [scheme, color, ink] of [['light', '#202020', 'dark'], ['dark', '#f0f0f0', 'light']]) {
    const preview = render(<div className={scheme === 'light' ? 'dark' : 'light'}><Preview scheme={scheme} background={{ enabled: true, color, opacity: 1 }} /></div>);
    const cover = preview.container.querySelector('[data-preview-cover]') as HTMLElement;
    expect([cover.style.backgroundColor, schemeOf(cover.querySelector('[data-loading-step]'))]).toEqual([color === '#202020' ? 'rgb(32, 32, 32)' : 'rgb(240, 240, 240)', ink]);
    cleanup();
  }
  vi.unstubAllGlobals();
});

// A document in a project leads its view's panel with the Project tab (`file-viewer/projectPanel.js`), the host's: before
// the view's own tabs, and as the whole panel of a view that has none of its own.
it("leads the view's panel with the project's list where the document is in one, and is the whole panel of a view with none", async () => {
  const { ProjectPanelContext } = await import('../../../../dist/file-viewer/projectPanel.js');
  const project = { label: 'Project', content: <p>the project's list</p> };
  // A wide view: the panel opens by its width, as it does for a file the person has not chosen for.
  const wide = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 1400, bottom: 900,
    width: 1400, height: 900, toJSON() {} } as DOMRect);
  const frame = (panel: object | null, value: object | null) => render(<ProjectPanelContext.Provider value={value}>
    <ViewFrame file="part.stl" mobile={false} compact={false} chromeHidden={false} failed={false} tools={[]} layout={{}} onLayoutChange={() => {}} panel={panel}>{null}</ViewFrame>
  </ProjectPanelContext.Provider>);
  const panelOf = (view: ReturnType<typeof render>) => view.container.querySelector('aside[data-flat-panel]');
  // No panel of its own and no project: none.
  expect(panelOf(frame(null, null))).toBeNull();
  cleanup();
  // No panel of its own, in a project: the panel is the Project tab, a lone title.
  let view = frame(null, project);
  expect([panelOf(view)?.querySelector('[data-flat-panel-heading]')?.textContent, view.getByText("the project's list") !== null]).toEqual(['Project', true]);
  cleanup();
  // A panel of its own: the Project tab first, then its tabs.
  view = frame({ kind: 'board', label: 'Board', searchLabel: 'Search', tabs: [{ id: 'layers', label: 'Layers', content: <p>layers</p> }] }, project);
  expect(view.getAllByRole('tab').map(tab => tab.getAttribute('data-flat-panel-tab') ?? tab.textContent)).toEqual(['project', 'layers']);
  wide.mockRestore();
});
