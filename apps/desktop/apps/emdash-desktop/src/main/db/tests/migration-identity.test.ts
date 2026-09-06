import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

type JournalEntry = {
  idx: number;
  tag: string;
  when: number;
};

type MigrationIdentity = JournalEntry & {
  hash: string;
};

const appRoot = fileURLToPath(new URL('../../../../', import.meta.url));
const journalPath = join(appRoot, 'drizzle/meta/_journal.json');
const goldenPath = fileURLToPath(new URL('./migration-identities.json', import.meta.url));

describe('migration identities', () => {
  it('keeps all shipped migration bytes and journal identities immutable', () => {
    const journal = JSON.parse(readFileSync(journalPath, 'utf8')) as {
      entries: JournalEntry[];
    };
    const golden = JSON.parse(readFileSync(goldenPath, 'utf8')) as MigrationIdentity[];
    const migrationsDir = dirname(dirname(journalPath));

    const actual = journal.entries.map(({ idx, tag, when }) => {
      const sqlBytes = readFileSync(join(migrationsDir, `${tag}.sql`));
      return {
        idx,
        tag,
        when,
        hash: createHash('sha256').update(sqlBytes).digest('hex'),
      };
    });

    expect(actual).toEqual(golden);
  });
});
