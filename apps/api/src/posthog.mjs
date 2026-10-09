/**
 * The store over PostHog (cadgen's telemetry: usage counts now, crash reports to come). Every row a batch
 * makes (`events.mjs`) becomes one PostHog event (`EVENTS`), with the install id as its distinct id, the
 * batch's context and the row's counts as properties, and the country the host placed the request in beside
 * them: never the IP address, nor anything finer. PostHog's own lookup of where an event came from is off
 * for every event (`$geoip_disable`): the receiver posts from the host's servers, so it would place everyone
 * there. An event is a window's counts, so a product reads them by adding up a property (`calls`, `count`,
 * `seconds`), never by counting events.
 *
 * An opt-out deletes the install's person and every event under its id (`/forget`): PostHog does that in the
 * background, so what "deleted" means is "queued for deletion". Retention is PostHog's: events go after the
 * period its plan keeps them.
 *
 * Its settings are the host's (api/v1.js): the project's API key, which captures; a personal API key with
 * `person:write`, which deletes, and `project:read`, which checks the project is there; the project's id; and
 * its region, `us` or `eu`. `fetch` is handed in, so the tests need no network.
 */

import { FIELDS } from './events.mjs';

// PostHog's name for each kind of row, as a product reads them.
export const EVENTS = {
  tool: 'tool_used', view: 'view_used', files: 'files_shown', build: 'models_built', snapshot: 'snapshots_rendered',
  feature: 'feature_used', health: 'daemon_health', exception: '$exception', tool_failure: 'tool_failed',
};
// Frames that name no file of ours: never in the app, whatever the code around them.
const NOT_OURS = new Set(['<user>', '<?>', '<frozen>']);
// What a row says beside its own fields, from the batch it came in.
const CONTEXT = ['process', 'version', 'channel', 'source', 'platform', 'arch', 'client', 'client_version', 'presentation'];
export const SETTINGS = ['POSTHOG_REGION', 'POSTHOG_PROJECT_KEY', 'POSTHOG_PERSONAL_KEY', 'POSTHOG_PROJECT_ID'];
const REGIONS = new Set(['us', 'eu']);
const TIMEOUT_MS = 8000; // well inside a function's own limit: a PostHog that hangs is a failure, and the batch waits

/** The settings a host lacks, by name -- missing, or not what PostHog would take (health says so). */
export function missingSettings(env) {
  const valid = {
    POSTHOG_REGION: value => REGIONS.has(value),
    POSTHOG_PROJECT_ID: value => /^\d+$/.test(value ?? ''),
  };
  return SETTINGS.filter(name => !(env[name] && (valid[name] ?? Boolean)(env[name])));
}

/** The store's settings, from the host's environment. */
export function settingsOf(env) {
  return { region: env.POSTHOG_REGION, projectKey: env.POSTHOG_PROJECT_KEY, personalKey: env.POSTHOG_PERSONAL_KEY,
    projectId: env.POSTHOG_PROJECT_ID };
}

/** An exit status as its platform writes it: a Windows exception code in hex (0xC0000005), anything else as is. */
const statusOf = status => (status >= 0xC0000000 ? `0x${status.toString(16).toUpperCase()}` : `${status}`);

/**
 * A crash as PostHog's error tracking reads one (`$exception_list`): its type, a value that is only ever
 * a dead worker's exit status, whether the process went on, and its frames, oldest first -- Python's,
 * or a page's JavaScript -- with only cadgen's own (or the page's) in the app.
 */
export function exceptionOf(row) {
  const page = row.where === 'page';
  const frames = row.frames.map(frame => ({
    platform: page ? 'web:javascript' : 'python', filename: frame.file, function: frame.function,
    ...(frame.line ? { lineno: frame.line } : {}), ...(frame.column ? { colno: frame.column } : {}),
    // PostHog resolves a page's frame through the source map the release uploaded under this id.
    ...(page && frame.chunk_id ? { chunk_id: frame.chunk_id } : {}),
    in_app: page ? !NOT_OURS.has(frame.file) : frame.file.startsWith('cadgen/'),
  }));
  return [{
    type: row.type, value: row.status === undefined ? '' : `exit status ${statusOf(row.status)}`,
    mechanism: { type: 'generic', handled: row.handled, synthetic: false },
    ...(frames.length ? { stacktrace: { type: 'raw', frames } } : {}),
  }];
}

/** A row as PostHog properties: its context, its own fields, and where it came from; nothing unset. */
export function propertiesOf(row, country) {
  // The session twice: `session`, which the counts are read by, and PostHog's own `$session_id`, which error
  // tracking counts an issue's sessions by. A process's id is a UUIDv4, not the v7 PostHog's sessions table
  // wants, so it sits out that table's aggregations; nothing else reads it.
  const properties = { distinct_id: row.install_id, session: row.session_id, $session_id: row.session_id, $geoip_disable: true };
  const fields = row.event === 'exception' ? ['where', 'tool', 'count'] : FIELDS[row.event];
  for (const key of [...CONTEXT, ...fields]) if (row[key] !== null && row[key] !== undefined) properties[key] = row[key];
  if (row.event === 'exception') properties.$exception_list = exceptionOf(row);
  if (country) properties.country = country;
  return properties;
}

/**
 * @param {{ region: string, projectKey: string, personalKey: string, projectId: string }} settings
 * @param {{ fetch?: typeof fetch }} [options]
 */
export function posthogStore({ region, projectKey, personalKey, projectId }, { fetch: send = fetch } = {}) {
  const capture = `https://${region}.i.posthog.com`;
  const api = `https://${region}.posthog.com/api/projects/${projectId}`;
  // Anything but a 2xx is the receiver's failure, never the client's: a 5xx tells it to keep its batch, or
  // the deletion it owes, and ask again. PostHog's answer is named by its status alone.
  const call = async (url, init) => {
    const response = await send(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
    if (!response.ok) throw Object.assign(new Error(`PostHog answered ${response.status}`), { code: `posthog_${response.status}` });
    return response;
  };
  const authorized = { authorization: `Bearer ${personalKey}` };
  return {
    /** @param {object[]} rows @param {{ country?: string | null }} [context] */
    async insert(rows, { country = null } = {}) {
      const batch = rows.map(row => ({ event: EVENTS[row.event], properties: propertiesOf(row, country) }));
      await call(`${capture}/batch/`, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ api_key: projectKey, batch }),
      });
    },
    async forget(install) {
      await call(`${api}/persons/bulk_delete/`, {
        method: 'POST', headers: { 'content-type': 'application/json', ...authorized },
        body: JSON.stringify({ distinct_ids: [install], delete_events: true }),
      });
    },
    // Health's question, every setting at once: the region and the id name a project that answers to the
    // personal key, and the capture key is that project's own (`api_token`). A key from another project would
    // put every batch there; one PostHog does not know would lose them all, unseen until someone looked.
    async ready() {
      const project = await (await call(`${api}/`, { headers: authorized })).json().catch(() => ({}));
      if (typeof project?.api_token === 'string' && project.api_token !== projectKey) {
        throw Object.assign(new Error("POSTHOG_PROJECT_KEY is not this project's"), { code: 'posthog_project_key' });
      }
    },
  };
}
