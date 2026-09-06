import { err, ok } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import {
  checkoutSelector,
  gitFilePath,
  mutationResult,
  repositorySelector,
} from './runtime-client';

describe('Git runtime client inputs', () => {
  it('creates structured selectors and portable file paths', () => {
    expect(repositorySelector('/repo').repository).toMatchObject({
      root: { kind: 'posix' },
      segments: ['repo'],
    });
    expect(checkoutSelector('/repo').checkout).toMatchObject({
      root: { kind: 'posix' },
      segments: ['repo'],
    });
    expect(gitFilePath('src\\file.ts')).toBe('src/file.ts');
  });

  it('unwraps Wire mutation data without changing failures', async () => {
    await expect(mutationResult(Promise.resolve(ok({ data: { hash: 'abc' } })))).resolves.toEqual(
      ok({ hash: 'abc' })
    );
    const failure = err({ type: 'git_error' as const, message: 'failed' });
    await expect(mutationResult(Promise.resolve(failure))).resolves.toEqual(failure);
  });
});
