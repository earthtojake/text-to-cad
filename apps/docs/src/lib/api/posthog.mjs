/**
 * The store over PostHog (cadgen's telemetry: usage counts now, crash reports to come). Every row a batch
 * makes (`events.mjs`) becomes one PostHog event, with the install id as its distinct id and the batch's
 * context as properties, and the country the host placed the request in beside them: never the IP address,
 * nor anything finer. PostHog's own lookup of where an event came from is off for every event
 * (`$geoip_disable`): the receiver posts from the host's servers, so it would place everyone there.
 *
 * An opt-out deletes the install's person and every event under its id (`/forget`): PostHog does that in the
 * background, so what "deleted" means is "queued for deletion". Retention is PostHog's: events go after the
 * period its plan keeps them.
 *
 * Its settings are the host's (route.ts): the project's API key, which captures; a personal API key with
 * `person:write`, which deletes and checks the project is there; the project's id; and its region, `us` or
 * `eu`. `fetch` is handed in, so the tests need no network.
 */

// PostHog's name for each kind of row, as a product reads them.
export const EVENTS = { tool: 'tool_used', view: 'view_used', file: 'file_shown' };
// What a row says beside its own fields, from the batch it came in.
const CONTEXT = ['version', 'channel', 'source', 'platform', 'arch', 'client', 'client_version', 'presentation'];
const FIELDS = { tool: ['tool', 'calls', 'errors'], view: ['calls'], file: ['file', 'kind'] };
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

/** A row as PostHog properties: its context, its own fields, and where it came from; nothing unset. */
export function propertiesOf(row, country) {
  const properties = { distinct_id: row.install_id, session: row.session_id, $geoip_disable: true };
  for (const key of [...CONTEXT, ...FIELDS[row.event]]) if (row[key] !== null && row[key] !== undefined) properties[key] = row[key];
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
    // Health's question: does the project answer to this key? (The capture key is checked by the first batch.)
    async ready() {
      await call(`${api}/`, { headers: authorized });
    },
  };
}
