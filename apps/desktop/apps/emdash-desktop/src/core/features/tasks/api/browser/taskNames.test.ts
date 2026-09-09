import { describe, expect, it } from 'vitest';
import {
  ensureUniqueTaskName,
  liveTransformTaskName,
  normalizeTaskName,
  taskNameCollisionKey,
} from './taskNames';

describe('taskNames', () => {
  it('lowercases task names by default when transforming task names', () => {
    expect(liveTransformTaskName('feature PROJ-123')).toBe('feature-proj-123');
  });

  it('lowercases task names by default when normalizing task names', () => {
    expect(normalizeTaskName('  feature PROJ-123  ')).toBe('feature-proj-123');
  });

  it('preserves capital letters when configured', () => {
    expect(liveTransformTaskName('feature PROJ-123', { preserveCapitalization: true })).toBe(
      'feature-PROJ-123'
    );
    expect(normalizeTaskName('  feature PROJ-123  ', { preserveCapitalization: true })).toBe(
      'feature-PROJ-123'
    );
  });

  it('normalizes task names to a case-insensitive collision key', () => {
    expect(taskNameCollisionKey('  feature PROJ-123  ')).toBe('feature-proj-123');
  });

  it('keeps generated unique task names distinct case-insensitively', () => {
    expect(ensureUniqueTaskName('Feature-PROJ-123', ['feature-proj-123'])).toBe(
      'feature-proj-123-2'
    );
  });

  it('keeps generated unique task names capitalized when configured', () => {
    expect(
      ensureUniqueTaskName('Feature-PROJ-123', ['feature-proj-123'], 6, {
        preserveCapitalization: true,
      })
    ).toBe('Feature-PROJ-123-2');
  });
});
