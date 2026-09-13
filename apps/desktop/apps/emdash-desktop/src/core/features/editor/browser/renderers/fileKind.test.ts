import { describe, expect, it } from 'vitest';
import {
  getFileKind,
  isBinaryForDiff,
  isMonacoBackedKind,
  isPreviewableKind,
} from '@core/features/editor/api/browser/renderers/fileKind';

describe('fileKind', () => {
  it('treats csv as a Monaco-backed preview kind', () => {
    const kind = getFileKind('customers.csv');

    expect(kind).toBe('csv');
    expect(isMonacoBackedKind(kind)).toBe(true);
  });

  it('opens PDFs as non-editable previews', () => {
    const kind = getFileKind('drawings/bracket.pdf');

    expect(kind).toBe('pdf');
    expect(isPreviewableKind(kind)).toBe(true);
    expect(isMonacoBackedKind(kind)).toBe(false);
    expect(isBinaryForDiff('drawings/bracket.pdf')).toBe(true);
  });
});
