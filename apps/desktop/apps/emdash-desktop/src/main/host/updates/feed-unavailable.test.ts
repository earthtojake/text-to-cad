import { describe, expect, it } from 'vitest';
import { isUpdateFeedUnavailable } from './utils';

describe('isUpdateFeedUnavailable', () => {
  it('recognises a missing or private release feed', () => {
    expect(
      isUpdateFeedUnavailable(Object.assign(new Error('not found'), { statusCode: 404 }))
    ).toBe(true);
    expect(isUpdateFeedUnavailable(Object.assign(new Error('forbidden'), { status: 403 }))).toBe(
      true
    );
    expect(
      isUpdateFeedUnavailable(
        new Error('HttpError: 404 "method: GET url: https://github.com/x/y/releases.atom"')
      )
    ).toBe(true);
    expect(isUpdateFeedUnavailable(new Error('Cannot find latest.yml in the latest release'))).toBe(
      true
    );
  });

  it('recognises an unreachable host', () => {
    expect(isUpdateFeedUnavailable(Object.assign(new Error('dns'), { code: 'ENOTFOUND' }))).toBe(
      true
    );
    expect(
      isUpdateFeedUnavailable(Object.assign(new Error('refused'), { code: 'ECONNREFUSED' }))
    ).toBe(true);
  });

  it('leaves real update failures alone', () => {
    expect(isUpdateFeedUnavailable(Object.assign(new Error('boom'), { statusCode: 500 }))).toBe(
      false
    );
    expect(isUpdateFeedUnavailable(new Error('sha512 checksum mismatch'))).toBe(false);
    expect(isUpdateFeedUnavailable(undefined)).toBe(false);
  });
});
