import type { WebContents } from 'electron';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { browserEvents } from '@core/features/browser/node';
import { desktopHostEvents } from '@core/features/workbench/node';
import { BrowserWebContentsRegistry } from './browser-webcontents-registry';

const sessionsByPartition = new Map<string, object>();

vi.mock('electron', () => ({
  clipboard: { writeImage: vi.fn() },
  session: {
    fromPartition: (partition: string) => {
      let value = sessionsByPartition.get(partition);
      if (!value) {
        value = { partition, getUserAgent: () => 'base-ua', clearData: vi.fn() };
        sessionsByPartition.set(partition, value);
      }
      return value;
    },
  },
}));

vi.mock('@core/features/browser/node', () => ({
  browserEvents: {
    emit: vi.fn(),
  },
}));
vi.mock('@core/features/workbench/node', () => ({
  desktopHostEvents: {
    emit: vi.fn(),
  },
}));

const PROFILE_PARTITION = 'persist:emdash-browser-profile';

type FakeWebContents = WebContents & {
  windowOpenHandler: Parameters<WebContents['setWindowOpenHandler']>[0] | null;
  destroy(): void;
  emitEvent(event: string, ...args: unknown[]): void;
};

let nextWebContentsId = 1;

function fakeWebContents(partition: string = PROFILE_PARTITION): FakeWebContents {
  const listeners = new Map<string, Array<(...args: unknown[]) => void>>();
  const fake = {
    id: nextWebContentsId++,
    session: sessionFor(partition),
    windowOpenHandler: null as FakeWebContents['windowOpenHandler'],
    close: vi.fn(),
    isDestroyed: () => false,
    getURL: () => 'https://example.com',
    getUserAgent: () => 'base-ua',
    setUserAgent: vi.fn(),
    openDevTools: vi.fn(),
    capturePage: vi.fn(),
    setWindowOpenHandler(handler: FakeWebContents['windowOpenHandler']) {
      fake.windowOpenHandler = handler;
    },
    on(event: string, listener: (...args: unknown[]) => void) {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
      return fake;
    },
    once(event: string, listener: (...args: unknown[]) => void) {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
      return fake;
    },
    destroy() {
      for (const listener of listeners.get('destroyed') ?? []) listener();
    },
    emitEvent(event: string, ...args: unknown[]) {
      for (const listener of listeners.get(event) ?? []) listener(...args);
    },
  };
  return fake as unknown as FakeWebContents;
}

function sessionFor(partition: string): object {
  let value = sessionsByPartition.get(partition);
  if (!value) {
    value = { partition, getUserAgent: () => 'base-ua', clearData: vi.fn() };
    sessionsByPartition.set(partition, value);
  }
  return value;
}

describe('BrowserWebContentsRegistry', () => {
  beforeEach(() => {
    sessionsByPartition.clear();
    vi.mocked(browserEvents.emit).mockClear();
    vi.mocked(desktopHostEvents.emit).mockClear();
  });

  it('closes attached webviews whose session has no registered partition', () => {
    const registry = new BrowserWebContentsRegistry();
    const webContents = fakeWebContents('persist:other');

    expect(registry.handleWebviewAttached(webContents)).toBe(false);
    expect(webContents.close).toHaveBeenCalled();
  });

  it('binds webviews on a shared partition to their browser ids explicitly', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });
    registry.registerSession({ browserId: 'browser-2', partition: PROFILE_PARTITION });

    const first = fakeWebContents();
    const second = fakeWebContents();
    expect(registry.handleWebviewAttached(first)).toBe(true);
    expect(registry.handleWebviewAttached(second)).toBe(true);

    expect(registry.bindWebContents('browser-1', first)).toBe(true);
    expect(registry.bindWebContents('browser-2', second)).toBe(true);

    expect(registry.openDevTools('browser-1')).toBe(true);
    expect(first.openDevTools).toHaveBeenCalled();
    expect(registry.getActiveBrowser()).toBe('browser-2');
  });

  it('closes a released native guest while retaining its registered session', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });
    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    expect(registry.releaseWebContents('browser-1')).toBe(true);
    expect(webContents.close).toHaveBeenCalledOnce();
    expect(registry.openDevTools('browser-1')).toBe(false);
    expect(registry.registeredPartitions).toContain(PROFILE_PARTITION);
  });

  it('captures the bound browser as an image for a chat attachment', async () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });
    const webContents = fakeWebContents();
    const image = { isEmpty: () => false };
    vi.mocked(webContents.capturePage).mockResolvedValue(image as never);

    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    await expect(registry.captureScreenshot('browser-1')).resolves.toBe(image);
  });

  it('rejects binding for unknown browsers, unattached or already-bound webContents', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });
    registry.registerSession({ browserId: 'browser-2', partition: PROFILE_PARTITION });

    const attached = fakeWebContents();
    registry.handleWebviewAttached(attached);

    expect(registry.bindWebContents('missing', attached)).toBe(false);
    expect(registry.bindWebContents('browser-1', fakeWebContents())).toBe(false);

    expect(registry.bindWebContents('browser-1', attached)).toBe(true);
    expect(registry.bindWebContents('browser-1', attached)).toBe(true);
    expect(registry.bindWebContents('browser-2', attached)).toBe(false);
  });

  it('rejects binding webContents from a different registered partition', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });
    registry.registerSession({
      browserId: 'browser-2',
      partition: 'persist:emdash-browser-profile-work',
    });

    const attached = fakeWebContents(PROFILE_PARTITION);
    registry.handleWebviewAttached(attached);

    expect(registry.bindWebContents('browser-2', attached)).toBe(false);
    expect(registry.bindWebContents('browser-1', attached)).toBe(true);
  });

  it('allows OAuth popups as hardened windows and routes tab links in-app', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    const handler = webContents.windowOpenHandler!;
    const popup = handler({
      url: 'https://github.com/login/oauth/authorize',
      disposition: 'new-window',
    } as Parameters<typeof handler>[0]);
    expect(popup.action).toBe('allow');
    expect(popup).toMatchObject({
      overrideBrowserWindowOptions: {
        webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
      },
    });

    const tab = handler({
      url: 'https://example.com/docs',
      disposition: 'foreground-tab',
    } as Parameters<typeof handler>[0]);
    expect(tab.action).toBe('deny');
    expect(browserEvents.emit).toHaveBeenCalledWith(undefined, {
      type: 'open-in-new-tab',
      sourceBrowserId: 'browser-1',
      url: 'https://example.com/docs',
    });

    const windowOpen = handler({
      url: 'https://example.com/popup',
      disposition: 'new-window',
    } as Parameters<typeof handler>[0]);
    expect(windowOpen.action).toBe('deny');
    expect(browserEvents.emit).toHaveBeenCalledWith(undefined, {
      type: 'open-in-new-tab',
      sourceBrowserId: 'browser-1',
      url: 'https://example.com/popup',
    });

    const blocked = handler({
      url: 'javascript:alert(1)',
      disposition: 'new-window',
    } as Parameters<typeof handler>[0]);
    expect(blocked.action).toBe('deny');
  });

  it('switches popup webContents user agent during Google auth navigations', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });
    const webContents = fakeWebContents();
    const popupWebContents = fakeWebContents();

    registry.handleWebviewAttached(webContents);
    webContents.emitEvent('did-create-window', { webContents: popupWebContents });
    popupWebContents.emitEvent(
      'did-start-navigation',
      {},
      'https://accounts.google.com/signin',
      false,
      true
    );

    expect(popupWebContents.setUserAgent).toHaveBeenCalledWith(
      expect.stringContaining('Firefox/140.0')
    );
  });

  it('cleans up bindings when the webContents is destroyed', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);
    expect(registry.getActiveBrowser()).toBe('browser-1');

    webContents.destroy();

    expect(registry.getActiveBrowser()).toBeNull();
    expect(registry.openDevTools('browser-1')).toBe(false);
  });

  it('emits tab navigation shortcuts from focused browser webContents', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    const keyEvent = { preventDefault: vi.fn() };
    webContents.emitEvent('before-input-event', keyEvent, {
      type: 'keyDown',
      key: 'Tab',
      control: true,
      shift: true,
      alt: false,
      meta: false,
    });

    expect(keyEvent.preventDefault).toHaveBeenCalled();
    expect(desktopHostEvents.emit).toHaveBeenCalledWith(undefined, {
      type: 'tab-navigation-shortcut',
      source: { kind: 'browser', browserId: 'browser-1' },
      direction: 'previous',
    });
  });

  it('emits app shortcuts from focused browser webContents', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    const keyEvent = { preventDefault: vi.fn() };
    webContents.emitEvent('before-input-event', keyEvent, {
      type: 'keyDown',
      key: 'K',
      control: process.platform !== 'darwin',
      shift: false,
      alt: false,
      meta: process.platform === 'darwin',
    });

    expect(keyEvent.preventDefault).toHaveBeenCalled();
    expect(desktopHostEvents.emit).toHaveBeenCalledWith(undefined, {
      type: 'browser-app-shortcut',
      source: { kind: 'browser', browserId: 'browser-1' },
      commandId: 'app.commandPalette',
    });
  });

  it('does not emit disabled app shortcuts from focused browser webContents', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.setKeyboardSettings({ commandPalette: null });
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    const keyEvent = { preventDefault: vi.fn() };
    webContents.emitEvent('before-input-event', keyEvent, {
      type: 'keyDown',
      key: 'K',
      control: process.platform !== 'darwin',
      shift: false,
      alt: false,
      meta: process.platform === 'darwin',
    });

    expect(keyEvent.preventDefault).not.toHaveBeenCalled();
    expect(desktopHostEvents.emit).not.toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ type: 'browser-app-shortcut' })
    );
  });

  it('does not claim text-input-gated shortcuts from browser webContents', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    const keyEvent = { preventDefault: vi.fn() };
    webContents.emitEvent('before-input-event', keyEvent, {
      type: 'keyDown',
      key: 'Backspace',
      control: process.platform !== 'darwin',
      shift: false,
      alt: false,
      meta: process.platform === 'darwin',
    });

    expect(keyEvent.preventDefault).not.toHaveBeenCalled();
    expect(desktopHostEvents.emit).not.toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ type: 'browser-app-shortcut' })
    );
  });

  it('does not consume Escape in focused browser webContents', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    const keyEvent = { preventDefault: vi.fn() };
    webContents.emitEvent('before-input-event', keyEvent, {
      type: 'keyDown',
      key: 'Escape',
      control: false,
      shift: false,
      alt: false,
      meta: false,
    });

    expect(keyEvent.preventDefault).not.toHaveBeenCalled();
    expect(desktopHostEvents.emit).not.toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ type: 'browser-app-shortcut' })
    );
  });

  it('does not consume shortcuts ignored in focused browser webContents', () => {
    const registry = new BrowserWebContentsRegistry();
    registry.registerSession({ browserId: 'browser-1', partition: PROFILE_PARTITION });

    const webContents = fakeWebContents();
    registry.handleWebviewAttached(webContents);
    registry.bindWebContents('browser-1', webContents);

    const keyEvent = { preventDefault: vi.fn() };
    webContents.emitEvent('before-input-event', keyEvent, {
      type: 'keyDown',
      key: 'Z',
      control: true,
      shift: false,
      alt: false,
      meta: false,
    });

    expect(keyEvent.preventDefault).not.toHaveBeenCalled();
    expect(desktopHostEvents.emit).not.toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ type: 'browser-app-shortcut' })
    );
  });

  it('clears storage for a named profile without requiring an open browser', async () => {
    const registry = new BrowserWebContentsRegistry();

    await expect(registry.clearProfileStorage('work')).resolves.toBe(true);
    await expect(registry.clearProfileStorage('isolated-per-task')).resolves.toBe(false);

    const clearedSession = [...sessionsByPartition.values()].find((value) => {
      const candidate = value as { clearData?: ReturnType<typeof vi.fn> };
      return candidate.clearData?.mock.calls.length;
    });
    expect(clearedSession).toBeDefined();
  });

  it('clears the requested browsing data category across every passed partition', async () => {
    const registry = new BrowserWebContentsRegistry();
    const partitions = [PROFILE_PARTITION, 'persist:emdash-browser-profile-work'];

    await expect(registry.clearBrowsingData('cache', partitions)).resolves.toBe(true);

    for (const partition of partitions) {
      const partitionSession = sessionsByPartition.get(partition) as
        | { clearData: ReturnType<typeof vi.fn> }
        | undefined;
      expect(partitionSession?.clearData).toHaveBeenCalledWith({ dataTypes: ['cache'] });
    }
  });

  it('passes no options for an "all" clear and dataTypes for other categories', async () => {
    const registry = new BrowserWebContentsRegistry();

    await registry.clearBrowsingData('all', [PROFILE_PARTITION]);
    await registry.clearBrowsingData('cookies', [PROFILE_PARTITION]);
    await registry.clearBrowsingData('siteData', [PROFILE_PARTITION]);

    const partitionSession = sessionsByPartition.get(PROFILE_PARTITION) as {
      clearData: ReturnType<typeof vi.fn>;
    };
    expect(partitionSession.clearData).toHaveBeenNthCalledWith(1);
    expect(partitionSession.clearData).toHaveBeenNthCalledWith(2, { dataTypes: ['cookies'] });
    expect(partitionSession.clearData).toHaveBeenNthCalledWith(3, {
      dataTypes: [
        'backgroundFetch',
        'cacheStorage',
        'fileSystems',
        'indexedDB',
        'localStorage',
        'serviceWorkers',
        'webSQL',
      ],
    });
  });
});
