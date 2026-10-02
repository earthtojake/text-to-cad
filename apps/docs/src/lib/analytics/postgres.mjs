/**
 * The store over any Postgres (`DATABASE_URL`: Neon through Vercel's marketplace today; Supabase,
 * RDS or a box of our own work the same). `schema.sql` creates its one table. The driver loads on
 * first use, so the site's build and the handler's tests need no database.
 */
const COLUMNS = ['install_id', 'session_id', 'event', 'tool', 'file', 'kind', 'calls', 'errors', 'version', 'source', 'platform', 'arch', 'client', 'client_version', 'presentation'];

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
    async forget(install) {
      const query = await db();
      await query`delete from events where install_id = ${install}`;
    },
    async prune(days) {
      const query = await db();
      const deleted = await query`delete from events where received_at < now() - make_interval(days => ${days})`;
      return deleted.count;
    },
  };
}
