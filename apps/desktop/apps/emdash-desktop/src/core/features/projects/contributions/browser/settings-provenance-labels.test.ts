import { describe, expect, it } from 'vitest';
import {
  brokenSettingText,
  provenanceBadgeLabel,
  provenanceSourceText,
} from './settings-provenance-labels';

describe('provenance rendering labels', () => {
  it('maps every provenance kind to a badge label', () => {
    expect(provenanceBadgeLabel({ kind: 'set' })).toBe('Set');
    expect(provenanceBadgeLabel({ kind: 'inferred', from: 'remote HEAD' })).toBe('Inferred');
    expect(provenanceBadgeLabel({ kind: 'broken-setting', staleValue: 'upstream' })).toBe('Broken');
    expect(provenanceBadgeLabel({ kind: 'unresolvable' })).toBe('Unavailable');
  });

  it('reads Inherited for the worktree-root flavor', () => {
    expect(provenanceBadgeLabel({ kind: 'inferred', from: 'host default' }, 'inherited')).toBe(
      'Inherited'
    );
    expect(provenanceBadgeLabel({ kind: 'set' }, 'inherited')).toBe('Set');
  });

  it('renders a source line only for inferred values', () => {
    expect(provenanceSourceText({ kind: 'inferred', from: 'remote HEAD' })).toBe(
      'from remote HEAD'
    );
    expect(provenanceSourceText({ kind: 'inferred', from: 'host default' })).toBe(
      'from the host default'
    );
    expect(provenanceSourceText({ kind: 'set' })).toBeNull();
    expect(provenanceSourceText({ kind: 'unresolvable' })).toBeNull();
  });

  it('falls back to the raw source for unknown inference sources', () => {
    expect(provenanceSourceText({ kind: 'inferred', from: 'somewhere new' })).toBe(
      'from somewhere new'
    );
  });

  it('describes broken settings with the stale value and live fallback', () => {
    expect(brokenSettingText('upstream', 'origin')).toBe(
      "Set to 'upstream' — not found, using 'origin'."
    );
    expect(brokenSettingText('upstream', null)).toBe(
      "Set to 'upstream' — not found, and no fallback could be inferred."
    );
  });
});
