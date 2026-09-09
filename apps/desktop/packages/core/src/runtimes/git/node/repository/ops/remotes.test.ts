import { describe, expect, it } from 'vitest';
import type { BoundExec } from '#services/exec/api';
import { computeRemotesState } from './remotes';

function createRemoteExec(stdout: string): BoundExec {
  return {
    file: 'git',
    cwd: '/repo',
    async exec(args) {
      expect(args).toEqual(['remote', '-v']);
      return { stdout, stderr: '' };
    },
    async execStreaming() {
      throw new Error('unexpected streaming Git execution');
    },
    async execBuffer() {
      throw new Error('unexpected buffered Git execution');
    },
    spawn() {
      throw new Error('unexpected spawned Git execution');
    },
    withCwd() {
      return this;
    },
  };
}

describe('computeRemotesState', () => {
  it('retains fetch remotes with partial-clone annotations', async () => {
    const exec = createRemoteExec(
      [
        'origin https://github.com/amywork777/hardcore (fetch) [blob:none]',
        'origin https://github.com/amywork777/hardcore (push)',
      ].join('\n')
    );

    await expect(computeRemotesState(exec)).resolves.toEqual({
      remotes: [{ name: 'origin', url: 'https://github.com/amywork777/hardcore' }],
    });
  });
});
