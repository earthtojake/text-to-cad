import { describe, expect, it } from 'vitest';
import {
  createDirectoryHistoryState,
  goBackDirectoryHistory,
  goForwardDirectoryHistory,
  pushDirectoryHistory,
} from './use-directory-history';

describe('directory history', () => {
  it('tracks back and forward navigation', () => {
    let state = createDirectoryHistoryState('/home/user');
    state = pushDirectoryHistory(state, '/home/user/repos');
    state = pushDirectoryHistory(state, '/home/user/repos/emdash');

    expect(state.entries).toEqual(['/home/user', '/home/user/repos', '/home/user/repos/emdash']);
    expect(state.index).toBe(2);

    state = goBackDirectoryHistory(state);
    expect(state.entries[state.index]).toBe('/home/user/repos');

    state = goForwardDirectoryHistory(state);
    expect(state.entries[state.index]).toBe('/home/user/repos/emdash');
  });

  it('truncates forward entries when navigating from the middle', () => {
    let state = createDirectoryHistoryState('/home/user');
    state = pushDirectoryHistory(state, '/home/user/repos');
    state = pushDirectoryHistory(state, '/home/user/repos/emdash');
    state = goBackDirectoryHistory(state);
    state = pushDirectoryHistory(state, '/home/user/downloads');

    expect(state.entries).toEqual(['/home/user', '/home/user/repos', '/home/user/downloads']);
    expect(state.entries[state.index]).toBe('/home/user/downloads');
  });

  it('does not duplicate the current path', () => {
    const state = createDirectoryHistoryState('/home/user');

    expect(pushDirectoryHistory(state, '/home/user')).toBe(state);
  });
});
