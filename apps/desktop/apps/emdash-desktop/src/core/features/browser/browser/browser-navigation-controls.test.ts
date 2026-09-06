import { describe, expect, it } from 'vitest';
import { decideBrowserReload } from './browser-navigation-controls';

describe('decideBrowserReload', () => {
  it('reloads a ready webview through its adapter', () => {
    expect(
      decideBrowserReload({
        currentUrl: 'https://example.com/',
        isLoading: false,
        hasAdapter: true,
      })
    ).toEqual({ kind: 'reload-adapter' });
  });

  it('stops loading through a ready webview adapter', () => {
    expect(
      decideBrowserReload({
        currentUrl: 'https://example.com/',
        isLoading: true,
        hasAdapter: true,
      })
    ).toEqual({ kind: 'stop-adapter' });
  });

  it('retries the current URL when the webview adapter is unavailable', () => {
    expect(
      decideBrowserReload({
        currentUrl: 'localhost:3000',
        isLoading: false,
        hasAdapter: false,
      })
    ).toEqual({ kind: 'retry-url', url: 'http://localhost:3000/' });
  });

  it('does nothing for unsupported URLs without a webview adapter', () => {
    expect(
      decideBrowserReload({
        currentUrl: 'javascript:alert(1)',
        isLoading: false,
        hasAdapter: false,
      })
    ).toEqual({ kind: 'noop' });
  });
});
