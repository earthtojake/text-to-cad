import { describe, expect, it } from 'vitest';
import {
  hardenBrowserWebviewPreferences,
  isBrowserPartition,
  stripBrowserWebviewParams,
  validateBrowserWebviewAttach,
  type WebviewPreferences,
} from './webview-security';

describe('browser webview security helpers', () => {
  it('recognizes only Hardcore browser partitions', () => {
    expect(isBrowserPartition('persist:hardcore-browser-profile')).toBe(true);
    expect(isBrowserPartition('persist:default')).toBe(false);
    expect(isBrowserPartition('temporary')).toBe(false);
  });

  it('requires registered browser partitions for webview attachment', () => {
    const partition = 'persist:hardcore-browser-project-workspace-task-browser';

    expect(
      validateBrowserWebviewAttach({ partition, src: 'https://example.com' }, new Set([partition]))
    ).toEqual({
      ok: true,
      partition,
      url: 'https://example.com/',
    });
    expect(validateBrowserWebviewAttach({ partition }, new Set())).toEqual({
      ok: false,
      reason: 'unregistered-partition',
    });
    expect(validateBrowserWebviewAttach({}, new Set())).toEqual({
      ok: false,
      reason: 'missing-partition',
    });
  });

  it('blocks unsupported initial webview URLs', () => {
    const partition = 'persist:hardcore-browser-project-workspace-task-browser';

    expect(
      validateBrowserWebviewAttach({ partition, src: 'javascript:alert(1)' }, new Set([partition]))
    ).toEqual({
      ok: false,
      reason: 'unsupported-url',
    });
    expect(
      validateBrowserWebviewAttach(
        { partition, src: 'mailto: user@example.com' },
        new Set([partition])
      )
    ).toEqual({
      ok: false,
      reason: 'unsupported-url',
    });
  });

  it('hardens Electron webview preferences', () => {
    const preferences: WebviewPreferences = {
      nodeIntegration: true,
      nodeIntegrationInSubFrames: true,
      nodeIntegrationInWorker: true,
      contextIsolation: false,
      sandbox: false,
      webSecurity: false,
      allowRunningInsecureContent: true,
      preload: '/tmp/untrusted.js',
    };

    hardenBrowserWebviewPreferences(preferences);

    expect(preferences).toEqual({
      nodeIntegration: false,
      nodeIntegrationInSubFrames: false,
      nodeIntegrationInWorker: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    });
  });

  it('strips untrusted webview attach params', () => {
    const params = {
      preload: '/tmp/untrusted.js',
      partition: 'persist:hardcore-browser-project-workspace-task-browser',
    };

    stripBrowserWebviewParams(params);

    expect(params).toEqual({
      partition: 'persist:hardcore-browser-project-workspace-task-browser',
    });
  });
});
