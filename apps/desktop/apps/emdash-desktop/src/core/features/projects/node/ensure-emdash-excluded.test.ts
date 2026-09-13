import { describe, expect, it, vi } from 'vitest';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { filesClientScope } from '@core/services/runtime-broker/node/files';
import { ensureEmdashGitExcluded } from './ensure-emdash-excluded';

type AbsoluteKey = { path: Parameters<typeof nativePathFromHost>[0] };

function relativeToRepo(key: AbsoluteKey): string {
  return nativePathFromHost(key.path).replace(/^\/repo\//, '');
}

function statResult(path: string, type: 'file' | 'directory') {
  return {
    success: true as const,
    data: {
      path,
      type,
      size: 0,
      mtimeMs: 0,
      ctimeMs: 0,
      mode: type === 'directory' ? 0o040755 : 0o100644,
    },
  };
}

function notFound(path: string) {
  return {
    success: false as const,
    error: {
      type: 'not-found' as const,
      path,
    },
  };
}

function makeFs(opts: {
  gitType?: 'directory' | 'file';
  excludeContent?: string | null;
  truncated?: boolean;
}) {
  const writeFile = vi.fn(async (_input: AbsoluteKey & { content: string }) => ({
    success: true as const,
    data: undefined,
  }));
  const client = {
    fs: {
      stat: vi.fn(async (key: AbsoluteKey) => {
        const relative = relativeToRepo(key);
        return relative === '.git' && opts.gitType
          ? statResult(relative, opts.gitType)
          : notFound(relative);
      }),
      exists: vi.fn(async () => ({
        success: true as const,
        data: { exists: opts.excludeContent != null },
      })),
      readText: vi.fn(async () => ({
        success: true as const,
        data: {
          content: opts.excludeContent ?? '',
          truncated: opts.truncated ?? false,
          totalSize: 0,
          etag: 'test-etag',
        },
      })),
      writeFile,
    },
  };
  return { files: filesClientScope(client as never, '/repo'), writeFile };
}

describe('ensureEmdashGitExcluded', () => {
  it('skips repos without a real .git directory (linked worktree / submodule)', async () => {
    const { files, writeFile } = makeFs({ gitType: 'file', excludeContent: '' });
    await ensureEmdashGitExcluded(files, '/repo');
    expect(writeFile).not.toHaveBeenCalled();
  });

  it('skips when there is no .git at all', async () => {
    const { files, writeFile } = makeFs({ excludeContent: '' });
    await ensureEmdashGitExcluded(files, '/repo');
    expect(writeFile).not.toHaveBeenCalled();
  });

  it('creates the exclude entry when info/exclude is missing', async () => {
    const { files, writeFile } = makeFs({ gitType: 'directory', excludeContent: null });
    await ensureEmdashGitExcluded(files, '/repo');
    expect(writeFile).toHaveBeenCalledWith(expect.objectContaining({ content: '.emdash/\n' }));
    expect(relativeToRepo(writeFile.mock.calls[0]![0])).toBe('.git/info/exclude');
  });

  it('appends the entry, preserving existing exclude content', async () => {
    const { files, writeFile } = makeFs({
      gitType: 'directory',
      excludeContent: '# git ls-files\nbuild/\n',
    });
    await ensureEmdashGitExcluded(files, '/repo');
    expect(writeFile).toHaveBeenCalledWith(
      expect.objectContaining({ content: '# git ls-files\nbuild/\n.emdash/\n' })
    );
    expect(relativeToRepo(writeFile.mock.calls[0]![0])).toBe('.git/info/exclude');
  });

  it('does nothing when .emdash/ is already excluded', async () => {
    const { files, writeFile } = makeFs({
      gitType: 'directory',
      excludeContent: 'foo\n.emdash/\n',
    });
    await ensureEmdashGitExcluded(files, '/repo');
    expect(writeFile).not.toHaveBeenCalled();
  });

  it('treats a slashless .emdash entry as already excluded', async () => {
    const { files, writeFile } = makeFs({ gitType: 'directory', excludeContent: '.emdash\n' });
    await ensureEmdashGitExcluded(files, '/repo');
    expect(writeFile).not.toHaveBeenCalled();
  });

  it('does not rewrite when the exclude read was truncated', async () => {
    // A truncated view could miss an existing entry past the cut; rewriting it would
    // drop the tail of the file, so bail instead.
    const { files, writeFile } = makeFs({
      gitType: 'directory',
      excludeContent: 'build/\n',
      truncated: true,
    });
    await ensureEmdashGitExcluded(files, '/repo');
    expect(writeFile).not.toHaveBeenCalled();
  });
});
