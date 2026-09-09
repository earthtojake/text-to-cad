import { describe, expect, it } from 'vitest';
import { browserLoadErrorCode, describeBrowserLoadError } from './browser-load-error';

describe('browser load error code', () => {
  it('normalizes Chromium error constants from the description', () => {
    expect(browserLoadErrorCode({ description: 'net::ERR_NAME_NOT_RESOLVED' })).toBe(
      'ERR_NAME_NOT_RESOLVED'
    );
  });

  it('resolves the constant from a numeric code when the description is human-readable', () => {
    expect(browserLoadErrorCode({ code: -105, description: 'Name not resolved' })).toBe(
      'ERR_NAME_NOT_RESOLVED'
    );
  });

  it('falls back to the raw numeric code, then null', () => {
    expect(browserLoadErrorCode({ code: -999, description: 'Something odd' })).toBe('Error -999');
    expect(browserLoadErrorCode({ description: '   ' })).toBeNull();
  });
});

describe('describeBrowserLoadError', () => {
  it('explains a DNS failure with the host name', () => {
    const presentation = describeBrowserLoadError(
      { code: -105, description: 'net::ERR_NAME_NOT_RESOLVED', url: 'https://sdfg.com/' },
      'https://sdfg.com/'
    );

    expect(presentation.heading).toBe("This site can't be reached");
    expect(presentation.detail).toBe("sdfg.com's server IP address could not be found.");
  });

  it('maps a refused connection from the numeric code alone', () => {
    const presentation = describeBrowserLoadError(
      { code: -102, description: 'Connection refused', url: 'http://localhost:3000/' },
      'http://localhost:3000/'
    );

    expect(presentation.detail).toBe('localhost refused to connect.');
  });

  it('uses an offline message when there is no internet', () => {
    const presentation = describeBrowserLoadError(
      { code: -106, description: 'net::ERR_INTERNET_DISCONNECTED' },
      'https://example.com/'
    );

    expect(presentation.heading).toBe('No internet');
    expect(presentation.detail).toBe('You appear to be offline.');
  });

  it('falls back to a human description for unknown codes', () => {
    const presentation = describeBrowserLoadError(
      { code: -999, description: 'something went wrong', url: 'https://example.com/' },
      'https://example.com/'
    );

    expect(presentation.heading).toBe("This site can't be reached");
    expect(presentation.detail).toBe('Something went wrong.');
  });

  it('falls back to the host when no useful description exists', () => {
    const presentation = describeBrowserLoadError(
      { description: '   ', url: 'https://example.com/path' },
      'https://example.com/path'
    );

    expect(presentation.detail).toBe('example.com could not be loaded.');
  });
});
