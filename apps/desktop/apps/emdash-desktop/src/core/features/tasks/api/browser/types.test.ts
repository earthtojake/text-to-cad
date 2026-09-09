import { describe, expect, it } from 'vitest';
import { visibleSidebarTab } from './types';

describe('visibleSidebarTab', () => {
  it('opens legacy Analysis sidebars as ordinary files', () => {
    expect(visibleSidebarTab('analysis')).toBe('files');
  });

  it('preserves current sidebar tabs', () => {
    expect(visibleSidebarTab('conversations')).toBe('conversations');
    expect(visibleSidebarTab('changes')).toBe('changes');
    expect(visibleSidebarTab('files')).toBe('files');
  });
});
