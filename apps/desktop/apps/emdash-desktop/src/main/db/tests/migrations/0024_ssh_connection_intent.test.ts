import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

describe('0024 ssh connection intent', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('adds nullable should_connect intent to SSH connections', async () => {
    fixture = await openFixture('pre-0024');

    const columns = fixture.sqlite.prepare(`PRAGMA table_info('ssh_connections')`).all() as {
      name: string;
      notnull: number;
    }[];

    expect(columns).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: 'should_connect',
          notnull: 0,
        }),
      ])
    );

    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, username)
         VALUES ('ssh-intent-null', 'Intent Null', 'host', 'user')`
      )
      .run();

    const row = fixture.sqlite
      .prepare(`SELECT should_connect FROM ssh_connections WHERE id = 'ssh-intent-null'`)
      .get() as { should_connect: number | null };
    expect(row.should_connect).toBeNull();
  });
});
