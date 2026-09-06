import { describe, expect, it } from 'vitest';
import { fileTreeModelSchema, isExpandableFileEntry } from './state';

const ROOT = { root: { kind: 'posix' as const }, segments: ['workspace'] };

describe('file tree state', () => {
  it('round-trips as JSON and derives symlink expansion from target kind', () => {
    const model = {
      root: ROOT,
      entries: {
        '': {
          path: '',
          name: 'workspace',
          parentPath: null,
          kind: 'directory' as const,
          childrenLoaded: true,
          children: ['linked'],
        },
        linked: {
          path: 'linked',
          name: 'linked',
          parentPath: '',
          kind: 'symlink' as const,
          symlinkTargetKind: 'directory' as const,
          childrenLoaded: false,
          children: [],
        },
      },
    };

    const parsed = fileTreeModelSchema.parse(JSON.parse(JSON.stringify(model)));
    expect(parsed).toEqual(model);
    expect(isExpandableFileEntry(parsed.entries.linked)).toBe(true);
    expect('expandable' in parsed.entries.linked).toBe(false);
  });

  it('rejects inconsistent normalized records', () => {
    expect(() =>
      fileTreeModelSchema.parse({
        root: ROOT,
        entries: {
          '': {
            path: '',
            name: 'workspace',
            parentPath: null,
            kind: 'directory',
            childrenLoaded: true,
            children: ['wrong'],
          },
          wrong: {
            path: 'different',
            name: 'wrong',
            parentPath: null,
            kind: 'file',
            childrenLoaded: false,
            children: [],
          },
        },
      })
    ).toThrow();
  });

  it('rejects children on files and symlinks without target classification', () => {
    expect(() =>
      fileTreeModelSchema.parse({
        root: ROOT,
        entries: {
          '': {
            path: '',
            name: 'workspace',
            parentPath: null,
            kind: 'directory',
            childrenLoaded: true,
            children: ['file.txt'],
          },
          'file.txt': {
            path: 'file.txt',
            name: 'file.txt',
            parentPath: '',
            kind: 'file',
            childrenLoaded: true,
            children: [],
          },
        },
      })
    ).toThrow();

    expect(() =>
      fileTreeModelSchema.parse({
        root: ROOT,
        entries: {
          '': {
            path: '',
            name: 'workspace',
            parentPath: null,
            kind: 'directory',
            childrenLoaded: true,
            children: ['linked'],
          },
          linked: {
            path: 'linked',
            name: 'linked',
            parentPath: '',
            kind: 'symlink',
            childrenLoaded: false,
            children: [],
          },
        },
      })
    ).toThrow();
  });
});
