import { describe, expect, it } from 'vitest';
import { builtInWorktreeRootFor, normalizeWorktreeRootPath } from './worktree-root';

describe('builtInWorktreeRootFor', () => {
  it('derives the posix built-in root under the home directory', () => {
    expect(builtInWorktreeRootFor('/home/me')).toBe('/home/me/emdash/worktrees');
  });

  it('ignores a trailing separator on the home directory', () => {
    expect(builtInWorktreeRootFor('/home/me/')).toBe('/home/me/emdash/worktrees');
  });

  it('derives the win32 built-in root with backslashes', () => {
    expect(builtInWorktreeRootFor('C:\\Users\\me')).toBe('C:\\Users\\me\\emdash\\worktrees');
  });
});

describe('normalizeWorktreeRootPath', () => {
  const home = '/home/me';

  it('accepts an absolute path unchanged', () => {
    expect(normalizeWorktreeRootPath('/srv/worktrees', home)).toBe('/srv/worktrees');
  });

  it('trims surrounding whitespace', () => {
    expect(normalizeWorktreeRootPath('  /srv/worktrees  ', home)).toBe('/srv/worktrees');
  });

  it('expands ~ to the home directory', () => {
    expect(normalizeWorktreeRootPath('~', home)).toBe('/home/me');
    expect(normalizeWorktreeRootPath('~/pool', home)).toBe('/home/me/pool');
  });

  it('rejects relative paths', () => {
    expect(normalizeWorktreeRootPath('relative/pool', home)).toBeNull();
    expect(normalizeWorktreeRootPath('./pool', home)).toBeNull();
  });

  it('rejects empty values', () => {
    expect(normalizeWorktreeRootPath('', home)).toBeNull();
    expect(normalizeWorktreeRootPath('   ', home)).toBeNull();
  });

  it('matches node path.normalize for messy posix inputs', () => {
    // Expected values are node's path.posix.normalize output (trailing
    // separator stripped); keep them in sync if normalize semantics change.
    expect(normalizeWorktreeRootPath('/a//b///c/', home)).toBe('/a/b/c');
    expect(normalizeWorktreeRootPath('/a/./b/../c', home)).toBe('/a/c');
    expect(normalizeWorktreeRootPath('/a/b/../../c/d', home)).toBe('/c/d');
    expect(normalizeWorktreeRootPath('/../a', home)).toBe('/a');
  });

  it('matches node path.normalize for messy win32 inputs', () => {
    const winHome = 'C:\\Users\\me';
    expect(normalizeWorktreeRootPath('C:\\a\\.\\b\\..\\c', winHome)).toBe('C:\\a\\c');
    expect(normalizeWorktreeRootPath('C:/a//b', winHome)).toBe('C:\\a\\b');
    expect(normalizeWorktreeRootPath('C:\\a\\b\\..\\..\\c', winHome)).toBe('C:\\c');
  });

  it('normalizes UNC roots without collapsing the server prefix', () => {
    expect(normalizeWorktreeRootPath('\\\\server\\share\\pool\\.\\x', 'C:\\Users\\me')).toBe(
      '\\\\server\\share\\pool\\x'
    );
  });

  it('expands ~ using a windows home directory', () => {
    expect(normalizeWorktreeRootPath('~/pool', 'C:\\Users\\me')).toBe('C:\\Users\\me\\pool');
  });
});
