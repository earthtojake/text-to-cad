/**
 * mention-grammar.test.ts — unit tests for the shared mention grammar.
 */

import { describe, expect, it } from 'vitest';
import { AT_BARE_PATTERN, SLASH_PATTERN, stringifyMention } from './mention-grammar';

// ── stringifyMention ─────────────────────────────────────────────────────────

describe('stringifyMention', () => {
  it('emits bare @label for non-file and non-issue kinds', () => {
    expect(
      stringifyMention({ label: 'handleSubmit', target: 'handleSubmit', kind: 'symbol' })
    ).toBe('@handleSubmit');
    expect(stringifyMention({ label: 'foo', target: 'foo', kind: 'custom' })).toBe('@foo');
    expect(stringifyMention({ label: 'foo', kind: null })).toBe('@foo');
  });

  it('emits bare @label when no target is provided', () => {
    expect(stringifyMention({ label: 'src/foo.ts', kind: 'file' })).toBe('@src/foo.ts');
  });

  it('emits @[label](target) bracket form for a file with target (no spaces)', () => {
    expect(stringifyMention({ label: 'jwt.ts', target: 'src/auth/jwt.ts', kind: 'file' })).toBe(
      '@[jwt.ts](src/auth/jwt.ts)'
    );
  });

  it('emits @[label](target) bracket form for an issue with target', () => {
    expect(
      stringifyMention({ label: 'ENG-123', target: 'issue:linear:ENG-123', kind: 'issue' })
    ).toBe('@[ENG-123](issue:linear:ENG-123)');
  });

  it('emits same label and target when label == target (no name override)', () => {
    expect(
      stringifyMention({ label: 'src/auth/jwt.ts', target: 'src/auth/jwt.ts', kind: 'file' })
    ).toBe('@[src/auth/jwt.ts](src/auth/jwt.ts)');
  });

  it('wraps target in angle brackets when it contains spaces', () => {
    expect(
      stringifyMention({
        label: 'foo.ts',
        target: '/Users/me/My Project/foo.ts',
        kind: 'file',
      })
    ).toBe('@[foo.ts](</Users/me/My Project/foo.ts>)');
  });

  it('wraps target in angle brackets when it contains parentheses', () => {
    expect(
      stringifyMention({
        label: 'foo (copy).ts',
        target: '/tmp/foo (copy).ts',
        kind: 'file',
      })
    ).toBe('@[foo (copy).ts](</tmp/foo (copy).ts>)');
  });

  it('wraps target containing both spaces and parens', () => {
    expect(
      stringifyMention({
        label: 'a.ts',
        target: '/my dir/some (thing)/a.ts',
        kind: 'file',
      })
    ).toBe('@[a.ts](</my dir/some (thing)/a.ts>)');
  });

  it('does NOT wrap an absolute path with no special chars', () => {
    expect(
      stringifyMention({
        label: 'main.ts',
        target: '/Users/me/projects/emdash/src/main.ts',
        kind: 'file',
      })
    ).toBe('@[main.ts](/Users/me/projects/emdash/src/main.ts)');
  });
});

// ── AT_BARE_PATTERN ───────────────────────────────────────────────────────────

describe('AT_BARE_PATTERN', () => {
  function matchBare(text: string): string | null {
    const re = new RegExp(AT_BARE_PATTERN, 'g');
    const m = re.exec(text);
    return m ? m[1] : null;
  }

  it('matches a simple file path', () => {
    expect(matchBare('@src/auth/jwt.ts')).toBe('src/auth/jwt.ts');
  });

  it('matches a dotfile', () => {
    expect(matchBare('@.gitignore')).toBe('.gitignore');
  });

  it('matches an issue ref with hyphen', () => {
    expect(matchBare('@issue-42')).toBe('issue-42');
  });

  it('matches a symbol with parens', () => {
    expect(matchBare('@handleSubmit()')).toBe('handleSubmit()');
  });

  it('does not absorb a trailing sentence-final dot', () => {
    expect(matchBare('@hello.ts.')).toBe('hello.ts');
  });

  it('does not match an @ without a valid token', () => {
    expect(matchBare('@ foo')).toBeNull();
  });
});

// ── SLASH_PATTERN ─────────────────────────────────────────────────────────────

describe('SLASH_PATTERN', () => {
  function matchSlash(text: string): string | null {
    const re = new RegExp(SLASH_PATTERN, 'g');
    const m = re.exec(text);
    return m ? m[1] : null;
  }

  it('matches a command at start of string', () => {
    expect(matchSlash('/review')).toBe('review');
  });

  it('matches a command after whitespace', () => {
    expect(matchSlash(' /explain')).toBe('explain');
  });

  it('does not match a slash in the middle of a path', () => {
    expect(matchSlash('path/to/file')).toBeNull();
  });

  it('does not match a URL path', () => {
    expect(matchSlash('https://example.com/path')).toBeNull();
  });

  it('matches a hyphenated command', () => {
    expect(matchSlash('/search-files')).toBe('search-files');
  });
});
