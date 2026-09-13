import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { getGitExecutable, GIT_EXECUTABLE, resolveGitBin, setGitExecutableOverride } from './exec';

const originalPlatform = process.platform;
let tempDir: string;

beforeEach(() => {
  setGitExecutableOverride(null);
  tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-git-bin-'));
});

afterEach(() => {
  setGitExecutableOverride(null);
  Object.defineProperty(process, 'platform', { value: originalPlatform });
  fs.rmSync(tempDir, { recursive: true, force: true });
});

function setPlatform(platform: NodeJS.Platform): void {
  Object.defineProperty(process, 'platform', { value: platform });
}

function executableGit(directory: string, filename = 'git'): string {
  fs.mkdirSync(directory, { recursive: true });
  const gitPath = path.join(directory, filename);
  fs.writeFileSync(gitPath, '#!/bin/sh\nexit 0\n', { mode: 0o755 });
  return gitPath;
}

describe('resolveGitBin', () => {
  it('prefers explicit GIT_PATH over PATH git', () => {
    const pathGit = executableGit(path.join(tempDir, 'path-bin'));
    const explicitGit = executableGit(path.join(tempDir, 'explicit-bin'));

    expect(resolveGitBin({ GIT_PATH: explicitGit, PATH: path.dirname(pathGit) })).toBe(explicitGit);
  });

  it('prefers PATH git before hardcoded fallbacks', () => {
    const pathGit = executableGit(path.join(tempDir, 'path-bin'));

    expect(resolveGitBin({ PATH: path.dirname(pathGit) })).toBe(pathGit);
  });

  it('skips invalid explicit GIT_PATH and falls back to PATH git', () => {
    const pathGit = executableGit(path.join(tempDir, 'path-bin'));

    expect(resolveGitBin({ GIT_PATH: '/does/not/exist', PATH: path.dirname(pathGit) })).toBe(
      pathGit
    );
  });

  it('finds PATHEXT executables on Windows PATH', () => {
    setPlatform('win32');
    const pathGit = executableGit(path.join(tempDir, 'path-bin'), 'git.exe');

    expect(resolveGitBin({ PATH: path.dirname(pathGit), PATHEXT: '.exe' })).toBe(pathGit);
  });

  it('uses the local host dependency override when present', () => {
    setGitExecutableOverride('/opt/homebrew/bin/git');

    expect(getGitExecutable()).toBe('/opt/homebrew/bin/git');

    setGitExecutableOverride(null);
    expect(getGitExecutable()).toBe(GIT_EXECUTABLE);
  });

  it('keeps remote host dependency overrides scoped by connection', () => {
    setGitExecutableOverride('/remote-a/bin/git', 'ssh-a');
    setGitExecutableOverride('/remote-b/bin/git', 'ssh-b');

    expect(getGitExecutable('ssh-a')).toBe('/remote-a/bin/git');
    expect(getGitExecutable('ssh-b')).toBe('/remote-b/bin/git');
    expect(getGitExecutable('ssh-c')).toBe('git');

    setGitExecutableOverride(null, 'ssh-a');
    setGitExecutableOverride(null, 'ssh-b');
    expect(getGitExecutable('ssh-a')).toBe('git');
  });
});
