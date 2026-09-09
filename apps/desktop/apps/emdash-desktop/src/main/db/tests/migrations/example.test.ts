/**
 * Example migration test — template for future migration authors.
 *
 * Pattern for writing a migration test:
 *
 *  1. Before writing your migration, snapshot the current baseline fixture:
 *       cp tooling/fixtures/baseline.db tooling/fixtures/pre-XXXX.db
 *     Commit this snapshot file together with your migration.
 *
 *  2. Write your migration (`pnpm run db:generate` after editing schema.ts).
 *
 *  3. Write a test here using `openFixture('pre-XXXX')`. The fixture already
 *     has data up to the previous migration; openFixture() will apply your new
 *     migration on top of it and give you a live DrizzleClient to assert
 *     against.
 *
 *  4. Regenerate the committed fixtures to pick up your new schema:
 *       pnpm run db:fixtures
 *
 *  5. Commit: migration SQL, pre-XXXX fixture, updated fixtures, this test.
 *
 * Running:
 *   pnpm run test:migrations
 */

import { openFixture } from '@tooling/utils/db';
import { count } from 'drizzle-orm';
import { afterEach, describe, expect, it } from 'vitest';
import { projects, tasks } from '@core/services/app-db/node/schema';

describe('baseline fixture integrity', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('has the expected tables after all migrations are applied', async () => {
    fixture = await openFixture('baseline');

    const tables = fixture.sqlite
      .prepare(`SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`)
      .all() as { name: string }[];

    const tableNames = tables.map((t) => t.name);
    expect(tableNames).toContain('projects');
    expect(tableNames).toContain('tasks');
    expect(tableNames).toContain('conversations');
    expect(tableNames).toContain('__drizzle_migrations');
  });

  it('has seeded projects and tasks in the baseline fixture', async () => {
    fixture = await openFixture('baseline');

    const [{ value: projectCount }] = await fixture.db.select({ value: count() }).from(projects);
    const [{ value: taskCount }] = await fixture.db.select({ value: count() }).from(tasks);

    expect(projectCount).toBe(3);
    expect(taskCount).toBe(5);
  });

  it('starts clean with the empty fixture', async () => {
    fixture = await openFixture('empty');

    const [{ value: projectCount }] = await fixture.db.select({ value: count() }).from(projects);

    expect(projectCount).toBe(0);
  });
});
