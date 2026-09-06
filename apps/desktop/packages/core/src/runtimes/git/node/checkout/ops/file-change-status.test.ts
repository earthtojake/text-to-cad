import { describe, expect, it } from 'vitest';
import { mapGitChangeStatus } from './status';

describe('diff parser', () => {
  it('maps git status codes', () => {
    expect(mapGitChangeStatus('??')).toBe('added');
    expect(mapGitChangeStatus(' D')).toBe('deleted');
    expect(mapGitChangeStatus('R100')).toBe('renamed');
    expect(mapGitChangeStatus('UU')).toBe('conflicted');
    expect(mapGitChangeStatus(' M')).toBe('modified');
  });
});
