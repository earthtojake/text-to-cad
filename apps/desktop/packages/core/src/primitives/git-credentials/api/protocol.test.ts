import { describe, expect, it } from 'vitest';
import { parseGitCredentialRequest, serializeGitCredentialResponse } from './protocol';

describe('parseGitCredentialRequest', () => {
  it('parses key=value lines into a record', () => {
    expect(parseGitCredentialRequest('protocol=https\nhost=github.com\n')).toEqual({
      protocol: 'https',
      host: 'github.com',
    });
  });

  it('keeps everything after the first "=" as the value', () => {
    expect(parseGitCredentialRequest('url=https://github.com/o/r?x=1\n')).toEqual({
      url: 'https://github.com/o/r?x=1',
    });
  });

  it('stops at the blank line that terminates a request', () => {
    expect(parseGitCredentialRequest('host=github.com\n\nusername=ignored\n')).toEqual({
      host: 'github.com',
    });
  });

  it('ignores malformed lines without an "="', () => {
    expect(parseGitCredentialRequest('garbage\nhost=github.com\n')).toEqual({
      host: 'github.com',
    });
  });

  it('keeps the last occurrence of a repeated key', () => {
    expect(parseGitCredentialRequest('wwwauth[]=Basic\nwwwauth[]=Bearer\n')).toEqual({
      'wwwauth[]': 'Bearer',
    });
  });

  it('tolerates CRLF line endings', () => {
    expect(parseGitCredentialRequest('protocol=https\r\nhost=github.com\r\n')).toEqual({
      protocol: 'https',
      host: 'github.com',
    });
  });

  it('parses an empty request to an empty record', () => {
    expect(parseGitCredentialRequest('')).toEqual({});
  });
});

describe('serializeGitCredentialResponse', () => {
  it('emits key=value lines with a trailing newline', () => {
    expect(serializeGitCredentialResponse({ username: 'octocat', password: 'tok' })).toBe(
      'username=octocat\npassword=tok\n'
    );
  });

  it('rejects values containing newlines or NUL (protocol injection)', () => {
    expect(() => serializeGitCredentialResponse({ username: 'a\nb' })).toThrow();
    expect(() => serializeGitCredentialResponse({ username: 'a\0b' })).toThrow();
    expect(() => serializeGitCredentialResponse({ 'bad\nkey': 'x' })).toThrow();
  });
});
