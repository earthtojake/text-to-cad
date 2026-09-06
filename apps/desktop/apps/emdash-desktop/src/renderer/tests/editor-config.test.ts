import { describe, expect, it } from 'vitest';
import { DIFF_EDITOR_BASE_OPTIONS } from '@core/features/editor/browser/monaco/editorConfig';

describe('DIFF_EDITOR_BASE_OPTIONS', () => {
  it('keeps unchanged diff regions visible for large text selection', () => {
    expect(DIFF_EDITOR_BASE_OPTIONS.hideUnchangedRegions?.enabled).toBe(false);
  });

  it('renders +/- gutter indicators for added and removed lines', () => {
    expect(DIFF_EDITOR_BASE_OPTIONS.renderIndicators).toBe(true);
  });
});
