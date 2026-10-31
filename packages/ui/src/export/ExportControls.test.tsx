import React from 'react';
import { cleanup, render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { ExportRequestError, exportPause } from '@text-to-cad/core/client';
import { ExportControls } from '../../dist/export/ExportControls.js';
import { useExportView } from '../../dist/export/context.js';
import { I18nProvider } from '../../dist/i18n/index.js';
import { ViewerMobileContext } from '../../dist/file-viewer/responsive.js';
import { ViewerElementContext, ViewerHostContext } from '../../dist/host/context.js';

// A retry's pause is the test's to end: a dropped connection is asked again when it says so.
vi.mock('@text-to-cad/core/client', async original => ({
  ...await original<typeof import('@text-to-cad/core/client')>(),
  exportPause: vi.fn(),
}));

Object.assign(globalThis, { React });
// jsdom has no pointer capture, which a press on a Sonner toast takes.
if (!HTMLElement.prototype.setPointerCapture) Object.assign(HTMLElement.prototype, { setPointerCapture() {}, releasePointerCapture() {} });
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { toast.dismiss(); cleanup(); vi.unstubAllGlobals(); });
const part = { doc: 'doc', revision: 'v1', file: '/part.xbf', name: 'part.xbf' };
type Shown = typeof part & { planar?: boolean };
function Document({ view }: { view: Shown }) { useExportView(view); return <div>Model</div>; }
const host = { environment: { colorScheme: 'light' } } as any;
function mount(service: any, downloads: any, { locale = 'en', phone = false, view = part as Shown, viewer = { current: null } as any } = {}) {
  // The overlay renders inside the viewer, which says whether its width is a phone's, its colour
  // scheme, and the element its navbar is in.
  return render(<I18nProvider locale={locale}><ExportControls service={service} downloads={downloads} file={view.file}>{({ navbar, overlay }: any) => <><nav>{navbar}</nav><Document view={view} />
    <ViewerHostContext.Provider value={host}><ViewerElementContext.Provider value={viewer}><ViewerMobileContext.Provider value={phone}>{overlay}</ViewerMobileContext.Provider></ViewerElementContext.Provider></ViewerHostContext.Provider></>}</ExportControls></I18nProvider>);
}
function server() {
  const waiting = new Map<string, { resolve(value: any): void; reject(error: unknown): void }>();
  const jobs = new Map<string, any>();
  const service = {
    epoch: vi.fn(async () => 'epoch'),
    create: vi.fn(async (request: any) => {
      const job = { ...request, id: request.requestId, filename: 'part.step', state: 'queued', stage: 'Waiting for worker', sequence: 0, createdAt: Date.now() / 1000 };
      jobs.set(job.id, job); return job;
    }),
    status: vi.fn((id: string, _sequence: number, signal: AbortSignal) => new Promise((resolve, reject) => {
      waiting.set(id, { resolve, reject }); signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    })),
    fileUrl: vi.fn((id: string) => `/s/session/__cad/exports/${id}/file`),
  };
  const answer = async (id: string, change: object) => act(async () => waiting.get(id)!.resolve({ ...jobs.get(id), sequence: 1, ...change }));
  const finish = (id: string) => answer(id, { state: 'ready', stage: 'Ready to save', bytes: 5, finishedAt: Date.now() / 1000, expiresAt: Date.now() / 1000 + 3600 });
  return { service, jobs, waiting, answer, finish };
}
const menu = () => screen.queryByRole('menu', { name: 'Export' });
async function exportOnce(user: ReturnType<typeof userEvent.setup>, format = 'STEP') {
  await user.click(screen.getByRole('button', { name: 'Export', exact: true }));
  await user.click(within(menu()!).getByRole('menuitem', { name: format }));
}
const toasts = () => [...document.querySelectorAll<HTMLElement>('[data-sonner-toast]')];
/** The one toast on screen: its Sonner type, its one line, whether it shows its state's icon, and its buttons. */
async function shown(type: 'loading' | 'success' | 'error', title: string) {
  await waitFor(() => expect(toasts().map(item => [item.dataset.type, item.querySelector('[data-title]')?.textContent])).toEqual([[type, title]]));
  const [item] = toasts();
  expect(item.querySelector('[data-description]')).toBeNull();
  expect(item.querySelector('[data-icon] svg')).toBeTruthy();
  return { item, buttons: [...item.querySelectorAll('button')].map(button => button.getAttribute('aria-label') || button.textContent) };
}

it('the menu is the formats the file\'s kind writes and nothing else, there at once: nothing is asked of the server before a choice', async () => {
  const kinds: [string, string[]][] = [
    ['/bracket.step', ['STEP', 'STL', '3MF', 'GLB', 'XBF']],
    ['/part.xbf', ['STEP', 'STL', '3MF', 'GLB', 'XBF']],
    ['0f8e2a7c-3b1d-5e4f-9a6b-7c8d9e0f1a2b', ['STEP', 'STL', '3MF', 'GLB', 'XBF']],
    ['/scene.glb', ['STL', '3MF']],
    ['/part.stl', ['3MF', 'GLB']],
    ['/kit.3mf', ['STL', 'GLB']],
  ];
  // A document the view draws flat on z=0 writes a DXF too; a mesh file never does.
  kinds.push(['/plate.xbf#planar', ['STEP', 'STL', '3MF', 'GLB', 'DXF', 'XBF']], ['/scene.glb#planar', ['STL', '3MF']]);
  for (const [shownFile, labels] of kinds) {
    const [file, planar] = [shownFile.replace('#planar', ''), shownFile.endsWith('#planar')];
    const { service } = server();
    const { unmount } = mount(service, { save: vi.fn() }, { view: { ...part, file, name: file.split('/').pop()!, ...(planar ? { planar } : {}) } });
    const user = userEvent.setup({ skipHover: true });
    await user.click(screen.getByRole('button', { name: 'Export', exact: true }));
    const items = within(menu()!).getAllByRole('menuitem');
    expect(items.map(item => item.textContent), shownFile).toEqual(labels);
    // Plain items alone: no checks, no icons, no heading, no button, no select, no rule, no note.
    for (const item of items) expect(item.querySelector('svg')).toBeNull();
    expect(within(menu()!).queryByRole('button')).toBeNull();
    expect(within(menu()!).queryByRole('combobox')).toBeNull();
    expect(within(menu()!).queryByRole('separator')).toBeNull();
    // As wide as its items, shadcn's least: no width of its own.
    expect(menu()!.className).toMatch(/(?:^|\s)min-w-\[8rem\](?:\s|$)/);
    expect(menu()!.className).not.toMatch(/(?:^|\s)w-/);
    expect([service.epoch, service.create].map(call => call.mock.calls.length)).toEqual([0, 0]);
    unmount();
  }
  // A view whose file writes nothing has no Export at all.
  const { service } = server();
  mount(service, { save: vi.fn() }, { view: { ...part, file: '/arm.urdf', name: 'arm.urdf' } });
  expect(screen.queryByRole('button', { name: 'Export', exact: true })).toBeNull();
});

it('a choice starts its export at once with a spinning toast; the menu stays the formats, and a second choice is another export', async () => {
  const { service } = server();
  const downloads = { save: vi.fn(), remember: vi.fn() };
  mount(service, downloads);
  const user = userEvent.setup({ skipHover: true });
  await exportOnce(user, 'GLB');
  await waitFor(() => expect(menu()).toBeNull());
  await waitFor(() => expect(service.create).toHaveBeenCalledTimes(1));
  expect(service.epoch).toHaveBeenCalledTimes(1);
  const request = service.create.mock.calls[0][0];
  expect(request).toEqual({ requestId: expect.any(String), epoch: 'epoch', source: { doc: 'doc', revision: 'v1' }, format: 'glb' });
  // Kept with its session's epoch while it is under way, so that a reload picks it up again.
  expect(downloads.remember).toHaveBeenLastCalledWith([{ request, filename: 'part.glb' }]);
  // The page's name for the file while it is made, in a spinner's single line with no buttons.
  const { item, buttons } = await shown('loading', 'Preparing part.glb…');
  expect(item.querySelector('[data-icon] svg.animate-spin')).toBeTruthy();
  expect(buttons).toEqual([]);
  await user.click(screen.getByRole('button', { name: 'Export', exact: true }));
  expect(within(menu()!).getAllByRole('menuitem').map(row => row.textContent)).toEqual(['STEP', 'STL', '3MF', 'GLB', 'XBF']);
  // An xbf's XBF is the file's own bytes: the server copies the original, never writes an xbf of an xbf.
  await user.click(within(menu()!).getByRole('menuitem', { name: 'XBF' }));
  await waitFor(() => expect(service.create).toHaveBeenCalledTimes(2));
  expect(service.create.mock.calls[1][0]).toMatchObject({ format: 'original', epoch: 'epoch' });
  await waitFor(() => expect(toasts()).toHaveLength(2));
  expect(downloads.save).not.toHaveBeenCalled();
});

it('a ready file is handed to the browser once, and its toast goes that moment: there is no success toast', async () => {
  const { service, jobs, finish } = server();
  const seen: (string | undefined)[] = [];
  // What the toast says at the moment the browser is handed the file: still that it is being prepared.
  const downloads = { save: vi.fn(() => { seen.push(toasts()[0]?.dataset.type); }), remember: vi.fn() };
  mount(service, downloads);
  const user = userEvent.setup({ skipHover: true });
  await exportOnce(user);
  await shown('loading', 'Preparing part.step…');
  const [id] = [...jobs.keys()];
  await finish(id);
  await waitFor(() => expect(toasts()).toEqual([]));
  expect(downloads.save).toHaveBeenCalledTimes(1);
  expect(downloads.save).toHaveBeenCalledWith(`/s/session/__cad/exports/${id}/file`, 'part.step');
  expect(seen).toEqual(['loading']);
  // Handed over, it is no longer kept, and its job is not asked about again.
  expect(downloads.remember).toHaveBeenLastCalledWith([]);
  expect(service.status).toHaveBeenCalledTimes(1);
});

it('an export the server refuses, or a job that fails, is an error toast with the engine\'s reason and a dismiss alone', async () => {
  const { service, jobs, answer } = server();
  service.create.mockRejectedValueOnce(new ExportRequestError('The source changed. Open Export again to use the displayed revision.', 409));
  const downloads = { save: vi.fn() };
  mount(service, downloads);
  const user = userEvent.setup({ skipHover: true });
  await exportOnce(user);
  const refused = await shown('error', 'The source changed. Open Export again to use the displayed revision.');
  expect(refused.buttons).toEqual(['Dismiss export status']);
  await user.click(within(refused.item).getByRole('button', { name: 'Dismiss export status' }));
  await waitFor(() => expect(toasts()).toEqual([]));
  await exportOnce(user, 'STL');
  await shown('loading', 'Preparing part.stl…');
  const [id] = [...jobs.keys()];
  await answer(id, { state: 'failed', stage: 'Export failed', error: 'STL needs a solid; this document holds none.', finishedAt: Date.now() / 1000 });
  expect((await shown('error', 'STL needs a solid; this document holds none.')).buttons).toEqual(['Dismiss export status']);
  expect(downloads.save).not.toHaveBeenCalled();
});

it('a dropped connection keeps the toast spinning until the poll resumes, then the export ends as it would have', async () => {
  const { service, jobs, waiting, finish } = server();
  const downloads = { save: vi.fn() };
  mount(service, downloads);
  const user = userEvent.setup({ skipHover: true });
  await exportOnce(user);
  await waitFor(() => expect(service.status).toHaveBeenCalledTimes(1));
  const [id] = [...jobs.keys()];
  let resume = () => {};
  vi.mocked(exportPause).mockImplementationOnce(() => new Promise<void>(resolve => { resume = resolve; }));
  await act(async () => waiting.get(id)!.reject(new TypeError('Failed to fetch')));
  await waitFor(() => expect(exportPause).toHaveBeenCalledWith(1000, expect.any(AbortSignal)));
  await shown('loading', 'Preparing part.step…');
  expect(service.status).toHaveBeenCalledTimes(1);
  // Asked again after its pause, it answers ready.
  await act(async () => resume());
  await waitFor(() => expect(service.status).toHaveBeenCalledTimes(2));
  await shown('loading', 'Preparing part.step…');
  await finish(id);
  await waitFor(() => expect(toasts()).toEqual([]));
  expect(downloads.save).toHaveBeenCalledTimes(1);
});

it('an export under way when the page reloaded picks up again by its request; one whose engine has gone since is its error', async () => {
  const { service } = server();
  const request = (id: string) => ({ requestId: id, epoch: 'epoch', source: { doc: 'doc', revision: 'v1' }, format: 'step' });
  service.create.mockImplementation(async value => {
    if (value.requestId === 'restarted') throw new ExportRequestError('The export session restarted. Open Export again.', 409);
    return { ...value, id: value.requestId, filename: 'kept.step', state: 'ready', stage: 'Ready to save', sequence: 1, createdAt: 1, finishedAt: 2, expiresAt: Date.now() / 1000 + 3600, bytes: 5 };
  });
  const downloads = { save: vi.fn(), remember: vi.fn(), restore: () => [{ request: request('kept'), filename: 'kept.step' }, { request: request('restarted'), filename: 'gone.step' }] };
  mount(service, downloads);
  // The one handed over has no toast left; the refused one says why.
  await waitFor(() => expect(toasts().map(item => [item.dataset.type, item.querySelector('[data-title]')?.textContent])).toEqual([
    ['error', 'The export session restarted. Open Export again.']]));
  expect(downloads.save).toHaveBeenCalledTimes(1);
  expect(downloads.save).toHaveBeenCalledWith('/s/session/__cad/exports/kept/file', 'kept.step');
  // Each names the session it was made in: a server restarted since refuses it, never runs it again.
  expect(service.epoch).not.toHaveBeenCalled();
  expect(downloads.remember).toHaveBeenLastCalledWith([]);
});

it('the keyboard opens the menu, walks it and chooses', async () => {
  const { service } = server();
  mount(service, { save: vi.fn() });
  const user = userEvent.setup({ skipHover: true });
  await user.tab();
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Export', exact: true }));
  await user.keyboard('{Enter}');
  await waitFor(() => expect(document.activeElement?.textContent).toBe('STEP'));
  await user.keyboard('{ArrowDown}');
  expect(document.activeElement?.textContent).toBe('STL');
  await user.keyboard('{Enter}');
  await waitFor(() => expect(service.create).toHaveBeenCalledTimes(1));
  expect(service.create.mock.calls[0][0].format).toBe('stl');
  await user.click(screen.getByRole('button', { name: 'Export', exact: true }));
  await user.keyboard('{Escape}');
  await waitFor(() => expect(menu()).toBeNull());
});

it('the menu and the toast speak the page language, never the server stage', async () => {
  const { service } = server();
  mount(service, { save: vi.fn() }, { locale: 'ja' });
  const user = userEvent.setup({ skipHover: true });
  await user.click(screen.getByRole('button', { name: 'エクスポート', exact: true }));
  await user.click(screen.getByRole('menuitem', { name: 'STEP' }));
  await shown('loading', 'part.step を準備中…');
  expect(screen.queryByText(/Waiting for worker/)).toBeNull();
});

it('the toasts stand at the top right under the viewer\'s navbar, by its 16px gutter, at every width', async () => {
  for (const phone of [false, true]) {
    const { service } = server();
    // The viewer's element and its navbar, which ends 48px down.
    const viewer = document.createElement('div');
    const bar = Object.assign(document.createElement('header'), { getBoundingClientRect: () => ({ top: 0, bottom: 48 }) });
    bar.setAttribute('data-viewer-navbar', '');
    viewer.append(bar);
    const { unmount } = mount(service, { save: vi.fn() }, { phone, viewer: { current: viewer } });
    const user = userEvent.setup({ skipHover: true });
    await exportOnce(user);
    await shown('loading', 'Preparing part.step…');
    const list = document.querySelector<HTMLElement>('[data-sonner-toaster]')!;
    expect([list.dataset.yPosition, list.dataset.xPosition]).toEqual(['top', 'right']);
    await waitFor(() => expect(['--offset-top', '--offset-right', '--mobile-offset-top', '--mobile-offset-right'].map(name => list.style.getPropertyValue(name)))
      .toEqual(['64px', '16px', '64px', '16px']));
    toast.dismiss();
    unmount();
  }
});
