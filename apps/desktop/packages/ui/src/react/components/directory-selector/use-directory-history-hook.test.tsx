/**
 * @vitest-environment jsdom
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useDirectoryHistory } from './use-directory-history';

describe('useDirectoryHistory', () => {
  it('exposes the destinations around the current history entry', () => {
    const { result } = renderHook(() => useDirectoryHistory('/home/user'));

    expect(result.current.backPath).toBeNull();
    expect(result.current.forwardPath).toBeNull();

    act(() => result.current.navigate('/home/user/repos'));
    expect(result.current.backPath).toBe('/home/user');
    expect(result.current.forwardPath).toBeNull();

    act(() => result.current.back());
    expect(result.current.backPath).toBeNull();
    expect(result.current.forwardPath).toBe('/home/user/repos');
  });
});
