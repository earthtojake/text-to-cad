import { describe, expect, it } from 'vitest';
import { parseAbsolute } from '#primitives/path/api';
import { gitFileContentKeySchema } from '#runtimes/git/api/checkout/file-content-key';
import { checkoutSelectorSchema, repositorySelectorSchema } from './selectors';

function root(input: string) {
  const parsed = parseAbsolute(input, { profile: { style: 'posix' } });
  if (!parsed.success) throw new Error(parsed.error.message);
  return parsed.data;
}

describe('Git path contracts', () => {
  it('uses host-local structured roots without a host routing field', () => {
    expect(repositorySelectorSchema.parse({ repository: root('/repo') })).toEqual({
      repository: root('/repo'),
    });
    expect(checkoutSelectorSchema.parse({ checkout: root('/repo/worktree') })).toEqual({
      checkout: root('/repo/worktree'),
    });
    expect(repositorySelectorSchema.safeParse({ repository: { path: '/repo' } }).success).toBe(
      false
    );
  });

  it('normalizes and confines Git file content paths to their checkout', () => {
    expect(
      gitFileContentKeySchema.parse({
        checkout: root('/repo'),
        path: 'src/./nested/../index.ts',
        source: { kind: 'head' },
      })
    ).toMatchObject({ path: 'src/index.ts', source: { kind: 'head' } });
    expect(
      gitFileContentKeySchema.safeParse({
        checkout: root('/repo'),
        path: '../outside',
        source: { kind: 'index' },
      }).success
    ).toBe(false);
    expect(
      gitFileContentKeySchema.safeParse({
        checkout: root('/repo'),
        path: '',
        source: { kind: 'head' },
      }).success
    ).toBe(false);
  });
});
