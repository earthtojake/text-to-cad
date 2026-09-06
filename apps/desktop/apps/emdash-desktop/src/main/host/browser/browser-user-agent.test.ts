import { describe, expect, it } from 'vitest';
import {
  firefoxUserAgent,
  isGoogleAuthUrl,
  stripEmbeddedBrowserTokens,
  userAgentForBrowserUrl,
} from './browser-user-agent';

const DEFAULT_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) ' +
  'emdash/1.1.32 Chrome/138.0.7204.97 Electron/40.7.0 Safari/537.36';

describe('stripEmbeddedBrowserTokens', () => {
  it('removes the Electron and app-name tokens', () => {
    expect(stripEmbeddedBrowserTokens(DEFAULT_UA, 'emdash')).toBe(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) ' +
        'Chrome/138.0.7204.97 Safari/537.36'
    );
  });

  it('leaves already-clean user agents untouched', () => {
    const clean =
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) ' +
      'Chrome/138.0.7204.97 Safari/537.36';
    expect(stripEmbeddedBrowserTokens(clean, 'emdash')).toBe(clean);
  });

  it('escapes regex metacharacters in the app name', () => {
    const ua = 'Mozilla/5.0 my.app+name/1.0 Chrome/138.0 Safari/537.36';
    expect(stripEmbeddedBrowserTokens(ua, 'my.app+name')).toBe(
      'Mozilla/5.0 Chrome/138.0 Safari/537.36'
    );
  });
});

describe('Google auth user agent override', () => {
  it('detects Google auth hosts only', () => {
    expect(isGoogleAuthUrl('https://accounts.google.com/o/oauth2/v2/auth')).toBe(true);
    expect(isGoogleAuthUrl('https://accounts.youtube.com/accounts/SetSID')).toBe(true);
    expect(isGoogleAuthUrl('https://www.google.com/search?q=test')).toBe(false);
    expect(isGoogleAuthUrl('https://accounts.google.com.evil.com/login')).toBe(false);
    expect(isGoogleAuthUrl('not a url')).toBe(false);
  });

  it('returns a Firefox user agent for Google auth URLs and the base elsewhere', () => {
    expect(userAgentForBrowserUrl('https://accounts.google.com/signin', DEFAULT_UA)).toContain(
      'Firefox/'
    );
    expect(userAgentForBrowserUrl('https://github.com/login', DEFAULT_UA)).toBe(DEFAULT_UA);
  });

  it('builds platform-specific Firefox user agents without Electron tokens', () => {
    for (const platform of ['darwin', 'win32', 'linux'] as const) {
      const ua = firefoxUserAgent(platform);
      expect(ua).toMatch(/^Mozilla\/5\.0 \(.+; rv:[\d.]+\) Gecko\/20100101 Firefox\/[\d.]+$/);
      expect(ua).not.toContain('Electron');
    }
  });
});
