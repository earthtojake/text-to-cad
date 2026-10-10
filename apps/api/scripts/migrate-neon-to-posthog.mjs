// ONE-OFF. Delete this file and its test (src/neon-migration.test.mjs) once the migration has run.
//
// Copies the usage analytics cadgen 0.7.7 to 0.7.15 sent before telemetry -- kept in Postgres on Neon by
// the receiver this site ran from 2026-10-02 until api.texttocad.dev forwarded to PostHog -- into
// PostHog, so the Neon database can be deleted.
//
// What moves. Each row of Neon's `events` table, as the receiver maps an old batch now: the stored rows of
// one batch are put back into the batch cadgen sent (schema 1 or 2) and read by the receiver's own
// `rowsOf` and `propertiesOf` (src/events.mjs, posthog.mjs). So a tool's calls are `tool_used`, a
// view's touches `view_used`, and files shown `files_shown`, a count by format. Each event keeps the time
// its batch arrived and its install id, so an opt-out deletes it like any other event. It is marked
// `migrated: neon`, and gets an id made from what it is, so a rerun sends the same events and PostHog
// keeps one of each. What does not move:
//   - the per-file codes (an HMAC of a path): the export leaves that column in Neon;
//   - a country: the old rows kept none (an event here has none either);
//   - the weekly and monthly installs-per-country totals, which name no install: exported to a CSV for
//     the record instead.
//
// When. Deploy Docs from main switches api.texttocad.dev from Neon to PostHog. Until the switch, an
// opt-out from cadgen 0.7.x deletes in Neon; after it, in PostHog. So the copy is made just BEFORE the
// switch, and nothing that reaches Neon after the copy is imported (a few minutes of counts, dropped:
// importing them after the switch could bring back an install that has opted out since). An install that
// opted out between the copy and the switch is then deleted from PostHog.
//
// Runbook, from the repository root, with psql and Node 22 (no npm install needed):
//
//   export NEON_DATABASE_URL='postgres://...'   # texttocad.dev's DATABASE_URL, from the Neon console
//   export POSTHOG_REGION=us POSTHOG_PROJECT_KEY=phc_... POSTHOG_PROJECT_ID=... POSTHOG_PERSONAL_KEY=phx_...
//   M=apps/api/scripts/migrate-neon-to-posthog.mjs
//
//   1. The copy, just before Deploy Docs:
//        psql "$NEON_DATABASE_URL" -At -c "$(node $M sql events)" > neon-events.jsonl
//        psql "$NEON_DATABASE_URL" -c "\copy (select * from countries order by period, starts, country) to 'neon-countries.csv' csv header"
//   2. Import it. Read the dry run's summary first; an import that stopped part way can simply be run again:
//        node $M import neon-events.jsonl --dry-run
//        node $M import neon-events.jsonl
//   3. Run Deploy Docs from main, and check https://api.texttocad.dev/v1/health answers {"ok":true}.
//   4. Who left between the copy and the switch, deleted from PostHog too:
//        psql "$NEON_DATABASE_URL" -At -c "$(node $M sql installs)" > neon-installs-after.txt
//        node $M forget neon-events.jsonl neon-installs-after.txt --dry-run
//        node $M forget neon-events.jsonl neon-installs-after.txt
//   5. In PostHog, the events filtered by `migrated = neon` add up to the dry run's counts. Then delete the
//      Neon database, remove DATABASE_URL and CRON_SECRET from the texttocad.dev project, retire the
//      t2c-analytics project, and delete the local exports but neon-countries.csv: they hold install ids.

import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

import { Invalid, isUuid, rowsOf } from '../src/events.mjs';
import { EVENTS, posthogStore, propertiesOf, settingsOf } from '../src/posthog.mjs';

// What the export reads of each row: every column but `file`, the per-file code, which never leaves Neon.
export const COLUMNS = ['id', 'received_at', 'install_id', 'session_id', 'event', 'tool', 'kind', 'calls', 'errors',
  'version', 'channel', 'source', 'platform', 'arch', 'client', 'client_version', 'presentation'];
const CHUNK = 500; // events a request to PostHog carries

/** The SQL each export runs: `events` (one JSON object a line) or `installs` (one id a line). */
export function sql(what) {
  if (what === 'events') return `select row_to_json(e) from (select ${COLUMNS.join(', ')} from events order by id) e;`;
  if (what === 'installs') return 'select distinct install_id from events order by 1;';
  throw new Error(`no export named ${what}: events or installs`);
}

/** The batches the rows were stored from: the rows of one arrival, from one process of one install. */
export function batchesOf(rows) {
  const batches = new Map();
  for (const row of rows) {
    const key = `${row.install_id} ${row.session_id} ${row.received_at}`;
    batches.set(key, [...batches.get(key) ?? [], row]);
  }
  return [...batches.values()];
}

/** One stored batch as cadgen sent it: schema 1 named how it was installed (`source`), schema 2 its channel. */
export function batchOf(rows) {
  const [first] = rows;
  const client = { ...first.client == null ? {} : { name: first.client },
    ...first.client_version == null ? {} : { version: first.client_version } };
  return {
    schema: first.source == null ? 2 : 1,
    install: first.install_id, session: first.session_id, version: first.version,
    ...first.source == null ? { channel: first.channel } : { source: first.source },
    platform: first.platform,
    ...first.arch == null ? {} : { arch: first.arch },
    ...Object.keys(client).length ? { client } : {},
    ...first.presentation == null ? {} : { presentation: first.presentation },
    events: rows.map(row => (row.event === 'tool' ? { name: 'tool', tool: row.tool, calls: row.calls, errors: row.errors }
      : row.event === 'view' ? { name: 'view', calls: row.calls }
      // The code that told a file apart stays in Neon: one made of the row's id stands in for it, and the
      // receiver drops it as it drops every code (a batch's files are a count by format).
      : { name: 'file', file: Number(row.id).toString(16).padStart(16, '0'), kind: row.kind })),
  };
}

// An id made from what an event is, laid out as a UUID: the same event, the same id, however often it is sent.
function idOf(text) {
  const hex = createHash('sha256').update(text).digest('hex');
  return [hex.slice(0, 8), hex.slice(8, 12), `4${hex.slice(13, 16)}`,
    (8 | (parseInt(hex[16], 16) & 3)).toString(16) + hex.slice(17, 20), hex.slice(20, 32)].join('-');
}

/** The PostHog events one stored batch makes: the receiver's rows and properties, at the time it arrived. */
export function eventsOf(rows) {
  const { install_id: install, session_id: session } = rows[0];
  const timestamp = new Date(rows[0].received_at).toISOString();
  return rowsOf(batchOf(rows)).map(row => ({
    event: EVENTS[row.event],
    timestamp,
    uuid: idOf(`neon ${install} ${session} ${timestamp} ${row.event} ${row.tool ?? row.kind ?? ''}`),
    properties: { ...propertiesOf(row, null), migrated: 'neon' },
  }));
}

/** The installs in the copy whose rows are gone from Neon now: each opted out after the copy. */
export function goneInstalls(rows, installsAfter) {
  const after = new Set(installsAfter);
  return [...new Set(rows.map(row => row.install_id))].filter(install => !after.has(install)).sort();
}

const lines = file => fs.readFileSync(file, 'utf8').split('\n').map(line => line.trim()).filter(Boolean);
const rowsIn = file => lines(file).map(line => JSON.parse(line));

function needs(env, names) {
  const settings = settingsOf(env);
  const missing = names.filter(name => !settings[name] || (name === 'region' && !['us', 'eu'].includes(settings[name])));
  if (missing.length) throw new Error(`set ${missing.map(name => ({ region: 'POSTHOG_REGION (us or eu)', projectKey: 'POSTHOG_PROJECT_KEY',
    personalKey: 'POSTHOG_PERSONAL_KEY', projectId: 'POSTHOG_PROJECT_ID' })[name]).join(', ')}`);
  return settings;
}

async function importEvents(file, { dryRun, env = process.env, send = fetch, log = console.log }) {
  const rows = rowsIn(file);
  const events = [];
  let refused = 0;
  for (const batch of batchesOf(rows)) {
    try {
      events.push(...eventsOf(batch));
    } catch (error) {
      if (!(error instanceof Invalid)) throw error;
      refused += 1; // what the receiver would refuse today: said, and left in Neon
      log(`  a batch the receiver refuses (${error.message}): ${batch.length} rows from id ${batch[0].id}, not imported`);
    }
  }
  const named = {};
  for (const event of events) named[event.event] = (named[event.event] ?? 0) + 1;
  const times = events.map(event => event.timestamp).sort();
  log(`${rows.length} rows (ids up to ${Math.max(0, ...rows.map(row => Number(row.id)))}), ${batchesOf(rows).length} batches `
    + `(${refused} refused), ${new Set(rows.map(row => row.install_id)).size} installs, ${times[0] ?? '-'} to ${times.at(-1) ?? '-'}`);
  log(`${events.length} events: ${JSON.stringify(named)}`);
  if (dryRun || !events.length) return;
  const { region, projectKey } = needs(env, ['region', 'projectKey']);
  for (let start = 0; start < events.length; start += CHUNK) {
    const response = await send(`https://${region}.i.posthog.com/batch/`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ api_key: projectKey, historical_migration: true, batch: events.slice(start, start + CHUNK) }),
    });
    if (!response.ok) throw new Error(`PostHog answered ${response.status} for events ${start} on: run the import again`);
    log(`  sent ${Math.min(start + CHUNK, events.length)} of ${events.length}`);
  }
}

async function forgetGone(eventsFile, installsFile, { dryRun, env = process.env, send = fetch, log = console.log }) {
  const gone = goneInstalls(rowsIn(eventsFile), lines(installsFile).filter(isUuid));
  log(`${gone.length} installs opted out between the copy and the switch`);
  if (dryRun || !gone.length) return;
  const store = posthogStore(needs(env, ['region', 'personalKey', 'projectId']), { fetch: send });
  for (const install of gone) await store.forget(install);
  log(`  deleted from PostHog: ${gone.length}`);
}

async function main([command, ...args]) {
  const dryRun = args.includes('--dry-run');
  const files = args.filter(arg => !arg.startsWith('--'));
  if (command === 'sql' && files.length === 1) return console.log(sql(files[0]));
  if (command === 'import' && files.length === 1) return importEvents(files[0], { dryRun });
  if (command === 'forget' && files.length === 2) return forgetGone(files[0], files[1], { dryRun });
  throw new Error('usage: sql events|installs | import EVENTS.jsonl [--dry-run] | forget EVENTS.jsonl INSTALLS.txt [--dry-run]');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).catch(error => {
    console.error(`migrate-neon-to-posthog: ${error.message}`);
    process.exit(1);
  });
}
