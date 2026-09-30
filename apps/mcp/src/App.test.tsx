import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';
import type { HostContext } from './host/bridge';
import type { Launch, Session } from './host/server';

beforeEach(() => vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

/** A host frame and CAD's server, as the page reaches them. */
function host(initial: HostContext) {
  const listeners = new Set<(context: HostContext) => void>();
  let context = initial;
  const bridge = {
    get hostContext() { return context; }, hostCapabilities: {},
    notify: vi.fn(), request: vi.fn(async () => ({})), callTool: vi.fn(),
    onToolResult: () => () => {}, onTeardown: () => () => {},
    onHostContext(listener: (next: HostContext) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    change(next: HostContext) { context = { ...context, ...next }; for (const listener of [...listeners]) listener(context); },
  };
  const server = {
    events: () => new Promise(() => {}), report: vi.fn(async () => ({})), reply: vi.fn(async () => ({})),
    recents: vi.fn(async () => []), thumbnails: vi.fn(async () => ({})),
  };
  return { bridge, server };
}
const session: Session = { protocol: 1, build: 'b', version: 'test', platform: 'darwin', workspace: [] };
const home: Launch = { protocol: 1, page: 'home', model: null, root: null, explore: false };
const sized = (notify: ReturnType<typeof vi.fn>) => notify.mock.calls.filter(([method]) => method === 'ui/notifications/size-changed');

it('a tab host gets the page it always had: full height, no card to size, no full-size button', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} launch={{ ...home, surface: 'sidebar' }} session={session} />);
  await screen.findByRole('button', { name: /Open Model/ });
  expect(screen.queryByRole('button', { name: 'Full size' })).toBeNull();
  expect(sized(bridge.notify)).toEqual([]);
});

it('an inline host gets a card of a height it is told, which goes full size in place', async () => {
  const { bridge, server } = host({ displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'] });
  render(<App bridge={bridge as any} server={server as any} presentation="inline" session={session}
    launch={{ ...home, surface: 'inline', view: 'cad-1-a', order: { createdAt: 1, seq: 1 } }} />);
  const openModel = await screen.findByRole('button', { name: /Open Model/ });
  expect(sized(bridge.notify)).toEqual([['ui/notifications/size-changed', { height: expect.any(Number) }]]);
  act(() => screen.getByRole('button', { name: 'Full size' }).click());
  expect(bridge.request).toHaveBeenCalledWith('ui/request-display-mode', { mode: 'fullscreen' });
  act(() => bridge.change({ displayMode: 'fullscreen' }));
  expect(screen.queryByRole('button', { name: 'Full size' })).toBeNull();
  // Full size keeps what was on the card: the same page, not a new one.
  expect(screen.getByRole('button', { name: /Open Model/ })).toBe(openModel);
});
