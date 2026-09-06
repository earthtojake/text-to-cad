import { describe, expect, it } from 'vitest';
import {
  toExpectedContentScopeError,
  toExpectedRootAccessError,
  toExpectedRootOrIndexError,
  toExpectedStoreError,
} from './error-mapping';
import { RootWatchError } from './path/index/errors';
import { hostPath as absolute } from './testing/paths';

describe('file-search error mapping', () => {
  const root = absolute('/workspace');

  it('classifies storage failures from SQLite only', () => {
    expect(
      toExpectedStoreError(
        root,
        Object.assign(new Error('database corrupt'), {
          code: 'ERR_SQLITE_ERROR',
          errcode: 11,
        }),
        'fallback'
      )
    ).toMatchObject({ type: 'io', message: 'database corrupt' });
    expect(
      toExpectedStoreError(
        root,
        Object.assign(new Error('too large'), { code: 'EFBIG' }),
        'fallback'
      )
    ).toBeUndefined();
    expect(
      toExpectedStoreError(
        root,
        Object.assign(new Error('constraint failed'), {
          code: 'ERR_SQLITE_ERROR',
          errcode: 19,
        }),
        'fallback'
      )
    ).toBeUndefined();
  });

  it('uses separate operational sets for root, path-index, and content-scope filesystem work', () => {
    const fileTooLarge = Object.assign(new Error('file too large'), { code: 'EFBIG' });
    const ioFailure = Object.assign(new Error('filesystem unavailable'), { code: 'EIO' });

    expect(toExpectedRootOrIndexError(root, fileTooLarge, 'fallback', 'root')).toBeUndefined();
    expect(toExpectedRootOrIndexError(root, fileTooLarge, 'fallback', 'path-index')).toMatchObject({
      type: 'io',
      message: 'file too large',
    });
    expect(toExpectedRootOrIndexError(root, ioFailure, 'fallback', 'root')).toMatchObject({
      type: 'io',
    });
    expect(toExpectedContentScopeError(root, ioFailure, 'fallback')).toMatchObject({ type: 'io' });
    expect(toExpectedContentScopeError(root, fileTooLarge, 'fallback')).toBeUndefined();
  });

  it('maps root access precisely and treats watcher attachment failures as operational', () => {
    expect(
      toExpectedRootAccessError(root, Object.assign(new Error('denied'), { code: 'EACCES' }))
    ).toMatchObject({ type: 'root-unavailable', reason: 'permission-denied' });
    expect(
      toExpectedRootOrIndexError(
        root,
        new RootWatchError(
          'File-search watcher could not attach to the root',
          new Error('watch backend unavailable')
        ),
        'fallback',
        'path-index'
      )
    ).toMatchObject({ type: 'io', message: 'watch backend unavailable' });
    expect(
      toExpectedRootOrIndexError(
        root,
        new RootWatchError(
          'File-search watcher could not be created for the root',
          Object.assign(new Error('root disappeared'), { code: 'ENOENT' })
        ),
        'fallback',
        'root'
      )
    ).toMatchObject({ type: 'root-unavailable', reason: 'not-found' });
  });

  it('does not hide unknown implementation failures', () => {
    expect(toExpectedStoreError(root, new Error('bug'), 'fallback')).toBeUndefined();
    expect(
      toExpectedRootOrIndexError(root, new Error('bug'), 'fallback', 'path-index')
    ).toBeUndefined();
    expect(toExpectedContentScopeError(root, new Error('bug'), 'fallback')).toBeUndefined();
  });
});
