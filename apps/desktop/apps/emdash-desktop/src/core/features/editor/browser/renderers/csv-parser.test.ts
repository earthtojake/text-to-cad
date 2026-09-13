import { describe, expect, it } from 'vitest';
import { parseCsv } from './csv-parser';

describe('parseCsv', () => {
  it('parses simple comma-separated rows', () => {
    expect(parseCsv('id,name\n1,Ada\n2,Grace').rows).toEqual([
      ['id', 'name'],
      ['1', 'Ada'],
      ['2', 'Grace'],
    ]);
  });

  it('handles quoted commas, escaped quotes, and quoted newlines', () => {
    expect(parseCsv('id,note\n1,"hello, world"\n2,"said ""hi"""\n3,"multi\nline"').rows).toEqual([
      ['id', 'note'],
      ['1', 'hello, world'],
      ['2', 'said "hi"'],
      ['3', 'multi\nline'],
    ]);
  });

  it('handles CRLF line endings', () => {
    expect(parseCsv('id,name\r\n1,Ada\r\n').rows).toEqual([
      ['id', 'name'],
      ['1', 'Ada'],
    ]);
  });
});
