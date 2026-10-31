import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from './harness/app.js';

// Which file generation owns what: two sources, two instances and opens superseded, over the
// harness's in-memory renderer (`harness/app.tsx`, the page the browser spec drives). None of it
// is layout or drawing, so it runs here; the explorer's layout and the renderer's re-renders on a
// resize are `FileViewer.browser.test.mjs`'s.
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const harness = () => (window as any).harness;
const payload = (testId = 'primary') => within(screen.getByTestId(testId)).queryByTestId('payload')?.textContent;
const shows = (text: string, testId = 'primary') => waitFor(() => expect(payload(testId)).toBe(text));
async function opened() {
  render(<App />);
  await shows('root-a notes');
}

it('sources, instances and cancelled opens stay isolated', async () => {
  await opened();
  act(() => harness().setRoot('root-b'));
  await shows('root-b notes');
  act(() => { harness().setRoot('root-a'); harness().second(true); });
  await shows('root-a notes');
  await shows('root-b notes', 'secondary');
  act(() => harness().second(false));
  act(() => harness().open('/work/slow.txt'));
  await within(screen.getByTestId('primary')).findByText(/Opening/);
  act(() => harness().open('/work/next.txt'));
  await shows('root-a next');
  expect(harness().events).toEqual(expect.arrayContaining(['root-a:aborted', 'root-b:/work/notes.txt:disposed']));
});

it("a former renderer cannot change the new source's state", async () => {
  await opened();
  const former = harness().rendererCallbacks.get('root-a');
  act(() => harness().setRoot('root-b'));
  await shows('root-b notes');
  act(() => former.onStateChange({ from: 'old root' }));
  expect(harness().state.renderers).toBeUndefined();
});

it('navbar actions belong to the active file generation and ignore retired registrations', async () => {
  await opened();
  const user = userEvent.setup({ skipHover: true });
  const current = harness().rendererCallbacks.get('root-a');
  const retired = current.onNavigationActionsChange;
  act(() => current.onNavigationActionsChange([{ id: 'fixture', label: 'Inspect notes', icon: 'span',
    onInvoke: () => harness().events.push('notes-action') }]));
  await user.click(await screen.findByRole('button', { name: 'Inspect notes' }));
  expect(harness().events).toContain('notes-action');
  // A hint shorter than the accessible name is the action's own field, not a special case in the navbar.
  act(() => current.onNavigationActionsChange([{ id: 'snapshot', label: 'Take snapshot', hint: 'Snapshot', icon: 'span', onInvoke() {} }]));
  const snapshot = await screen.findByRole('button', { name: 'Take snapshot' });
  await userEvent.setup().hover(snapshot);
  expect((await screen.findByRole('tooltip')).textContent).toBe('Snapshot');
  expect(snapshot.getAttribute('title')).toBeNull();
  act(() => harness().open('/work/next.txt'));
  await shows('root-a next');
  expect(screen.queryByRole('button', { name: 'Inspect notes' })).toBeNull();
  act(() => {
    harness().rendererCallbacks.get('root-a').onNavigationActionsChange([{ id: 'next', label: 'Inspect next', icon: 'span', onInvoke() {} }]);
    retired([]);
  });
  await screen.findByRole('button', { name: 'Inspect next' });
  act(() => retired([{ id: 'stale', label: 'Stale action', icon: 'span', onInvoke() {} }]));
  expect(screen.queryByRole('button', { name: 'Stale action' })).toBeNull();
  expect(screen.getAllByRole('button', { name: 'Inspect next' })).toHaveLength(1);
});

it('a departing renderer flushes its own state on file changes and reloads, but never into another source', async () => {
  await opened();
  const stored = (path: string) => harness().state.renderers?.[JSON.stringify([path, 'in-memory'])];
  act(() => { harness().cleanupWrites.set('root-a:/work/notes.txt', { selection: 'last frame' }); harness().open('/work/next.txt'); });
  await shows('root-a next');
  expect(stored('/work/notes.txt')).toEqual({ selection: 'last frame' });
  const mount = within(screen.getByTestId('primary')).getByTestId('mount').textContent;
  act(() => { harness().cleanupWrites.set('root-a:/work/next.txt', { annotation: 'pending stroke' }); harness().rendererCallbacks.get('root-a').reload(); });
  await waitFor(() => expect(within(screen.getByTestId('primary')).getByTestId('mount').textContent).not.toBe(mount));
  await shows('root-a next');
  expect(stored('/work/next.txt')).toEqual({ annotation: 'pending stroke' });
  act(() => { harness().cleanupWrites.set('root-a:/work/next.txt', { annotation: 'wrong source' }); harness().setRoot('root-b'); });
  await shows('root-b next');
  expect(stored('/work/next.txt')).toEqual({ annotation: 'pending stroke' });
});
