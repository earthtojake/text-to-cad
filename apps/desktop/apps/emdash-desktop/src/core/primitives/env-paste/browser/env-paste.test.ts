import { describe, expect, it } from 'vitest';
import { parseEnvAssignmentPaste, replaceEnvEntryWithPaste } from './env-paste';

describe('parseEnvAssignmentPaste', () => {
  it('parses dotenv-style assignments', () => {
    expect(
      parseEnvAssignmentPaste(`
        # ignored
        FOO=bar
        export API_KEY="secret=value"
        WITH_COMMENT=value # comment
        QUOTED_HASH="value # not a comment"
        EMPTY=
      `)
    ).toEqual([
      { key: 'FOO', value: 'bar' },
      { key: 'API_KEY', value: 'secret=value' },
      { key: 'WITH_COMMENT', value: 'value' },
      { key: 'QUOTED_HASH', value: 'value # not a comment' },
      { key: 'EMPTY', value: '' },
    ]);
  });

  it('rejects non-assignment paste content', () => {
    expect(parseEnvAssignmentPaste('not an env file')).toEqual([]);
    expect(parseEnvAssignmentPaste('FOO=bar\nnot an env file')).toEqual([]);
  });
});

describe('replaceEnvEntryWithPaste', () => {
  it('replaces the target row and preserves following rows', () => {
    const entries = [
      { key: 'KEEP', value: 'before' },
      { key: '', value: '' },
      { key: 'AFTER', value: 'after' },
    ];

    expect(
      replaceEnvEntryWithPaste(entries, 1, [
        { key: 'FOO', value: 'bar' },
        { key: 'BAZ', value: 'qux' },
      ])
    ).toEqual([
      { key: 'KEEP', value: 'before' },
      { key: 'FOO', value: 'bar' },
      { key: 'BAZ', value: 'qux' },
      { key: 'AFTER', value: 'after' },
    ]);
  });
});
