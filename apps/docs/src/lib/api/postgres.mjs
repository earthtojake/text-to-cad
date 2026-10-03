/**
 * The store over any Postgres (`DATABASE_URL`: Neon through Vercel's marketplace today; Supabase,
 * RDS or a box of our own work the same). `schema.sql` creates its tables. The driver loads on
 * first use, so the site's build and the handler's tests need no database. Weeks are ISO weeks
 * and months calendar months, both in UTC.
 */
const COLUMNS = ['install_id', 'session_id', 'event', 'tool', 'file', 'kind', 'calls', 'errors', 'version', 'channel', 'platform', 'arch', 'client', 'client_version', 'presentation'];

export function postgresStore(url) {
  let sql;
  const db = async () => {
    if (!url) throw new Error('DATABASE_URL is not set');
    const { default: postgres } = await import('postgres');
    return (sql ??= postgres(url, { max: 1, idle_timeout: 20, prepare: false }));
  };
  return {
    async insert(rows) {
      const query = await db();
      await query`insert into events ${query(rows, COLUMNS)}`;
    },
    async seen(install) {
      const query = await db();
      const [row] = await query`select
        exists(select 1 from events where install_id = ${install} and received_at >= date_trunc('week', now(), 'UTC')) as week,
        exists(select 1 from events where install_id = ${install} and received_at >= date_trunc('month', now(), 'UTC')) as month`;
      return { week: row.week, month: row.month };
    },
    async tally(country, periods) {
      const query = await db();
      for (const period of periods) {
        await query`insert into countries (period, starts, country, installs)
          values (${period}, (date_trunc(${period}, now(), 'UTC') at time zone 'UTC')::date, ${country}, 1)
          on conflict (period, starts, country) do update set installs = countries.installs + 1`;
      }
    },
    async forget(install) {
      const query = await db();
      await query`delete from events where install_id = ${install}`;
    },
    async prune(days) {
      const query = await db();
      const deleted = await query`delete from events where received_at < now() - make_interval(days => ${days})`;
      return deleted.count;
    },
    // Health's question: does every column a batch and the totals are written to exist? Read for no rows:
    // a schema change that schema.sql was not re-run for fails the deploy's check, as it would every batch.
    async ready() {
      const query = await db();
      await query`select ${query(COLUMNS)} from events limit 0`;
      await query`select period, starts, country, installs from countries limit 0`;
    },
  };
}
