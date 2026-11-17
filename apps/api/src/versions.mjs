/**
 * GET /v1/versions: the feed every installed text-to-cad reads (`cad_server/updates.py` in packages/cad-server):
 *
 *   {"latest": "0.9.0"}
 *
 * `latest` is THE POINTER: the one release cad's own update and the install command install (`cad==X`), and that
 * releases 0.10.0 to 0.11.11 install as `cad-server==X`. It is the newest release that
 *   1. has a file PyPI's simple index lists unyanked (a pre-release is no release here: the server reads only
 *      `X.Y.Z`), read from `cadgen`'s index: a release uploads its projects one at a time, `cad`, `cad-server`,
 *      `cad-mcp`, then `cadgen`, each only once PyPI lists the one before (.github/workflows/release-publish.yml),
 *      so a release `cadgen` lists can be installed by every name. `cad`'s own index is no use here: it also holds
 *      another owner's yanked 0.8 to 1.1.2 from 2020, and a release half uploaded is listed there first;
 *   2. is at least an hour old by PyPI's own upload time (`upload-time`) of every unyanked file of it: the hour in
 *      which a bad release can be held before any computer installs it. A file with no usable upload time makes
 *      its release not old enough;
 *   3. is not held: `held` is a set of `X.Y.Z` the feed never names, from the Vercel project's `CAD_HELD_RELEASES`
 *      (`heldOf`, README "Holding a release").
 * A release that is held or too new is passed over, never answered as nothing: the feed names the newest release
 * that qualifies.
 *
 * Each instance keeps what it last read for a few minutes, and keeps answering it while PyPI fails. With
 * nothing read yet and PyPI failing, there is no feed (`null`): the handler answers 503, which a released
 * server takes as a check that failed -- silently, keeping the feed it last read, and trying again an hour
 * later. `fetch` and `now` are handed in, so the tests need no network and no clock.
 */

export const INDEX = 'https://pypi.org/simple/cadgen/';
export const MIN_AGE_MS = 60 * 60 * 1000; // a release is named an hour after its last file reached PyPI
const RELEASE = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/; // `cad_server/updates.py`'s own `_RELEASE`
const FILE = /^cadgen-([^-]+?)(?:-.+\.whl|\.tar\.gz|\.zip)$/; // a wheel's or an sdist's name, and its version
const UPLOADED = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/; // PEP 700's ISO 8601
const TIMEOUT_MS = 3000; // well inside the server's own wait (5 s): a PyPI that hangs is a PyPI that failed
const FRESH_MS = 5 * 60 * 1000; // the edge keeps a reply far longer (handler.mjs); this only spares PyPI

const parts = version => version.split('.').map(Number);
const newer = (a, b) => {
  const [x, y] = [parts(a), parts(b)];
  return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
};
// PEP 691: `yanked` is false (or absent) for a file that is not, and true or the reason for one that is.
const unyanked = file => file.yanked === false || file.yanked === undefined;
const uploadedAt = file => {
  const at = typeof file['upload-time'] === 'string' && UPLOADED.test(file['upload-time']) ? Date.parse(file['upload-time']) : NaN;
  return Number.isFinite(at) ? at : null;
};

/**
 * The releases `X.Y.Z` the Vercel project holds back: `CAD_HELD_RELEASES`, versions separated by commas or
 * spaces. Anything else in it is ignored, and logged so a typo is seen.
 */
export function heldOf(env = {}, log = console.error) {
  const held = new Set();
  for (const word of String(env?.CAD_HELD_RELEASES ?? '').split(/[\s,]+/).filter(Boolean)) {
    if (RELEASE.test(word)) held.add(word);
    else log('version feed: CAD_HELD_RELEASES names no release:', JSON.stringify(word.slice(0, 40)));
  }
  if (held.size) log('version feed: holding', [...held].sort(newer).join(', '));
  return held;
}

/**
 * The pointer an index page (PEP 691 JSON) gives at `now`: the newest release with an unyanked file, every
 * unyanked file of it uploaded at least an hour before `now`, and not in `held`; `null` when none is.
 */
export function latestOf(page, { now = Date.now(), held = new Set() } = {}) {
  const uploaded = new Map(); // release -> when its last unyanked file was uploaded, or null when unknown
  for (const file of Array.isArray(page?.files) ? page.files : []) {
    if (!file || typeof file !== 'object' || !unyanked(file)) continue;
    const version = FILE.exec(typeof file.filename === 'string' ? file.filename : '')?.[1];
    if (!version || !RELEASE.test(version)) continue;
    const at = uploadedAt(file);
    const before = uploaded.has(version) ? uploaded.get(version) : -Infinity;
    uploaded.set(version, at === null || before === null ? null : Math.max(before, at));
  }
  const ready = [...uploaded].filter(([version, at]) => at !== null && now - at >= MIN_AGE_MS && !held.has(version));
  return ready.map(([version]) => version).sort(newer).at(-1) ?? null;
}

/**
 * The feed, read from PyPI: a function the handler calls, which answers `{latest}` or `null`, and never
 * throws.
 */
export function pypiVersions({ fetch = globalThis.fetch, now = Date.now, log = console.error, timeout = TIMEOUT_MS, held = new Set() } = {}) {
  let kept = null; // { feed, at }; a failed first read keeps a null feed until the next attempt
  let asking = null;
  async function ask() {
    try {
      const response = await fetch(INDEX, {
        headers: { accept: 'application/vnd.pypi.simple.v1+json' },
        signal: AbortSignal.timeout(timeout),
      });
      if (!response.ok) throw Object.assign(new Error('PyPI refused'), { code: `pypi_${response.status}` });
      const latest = latestOf(await response.json(), { now: now(), held });
      if (!latest) throw Object.assign(new Error('no release'), { code: 'pypi_no_release' });
      kept = { feed: Object.freeze({ latest }), at: now() };
    } catch (error) {
      log('version feed: PyPI failed:', error?.code ?? error?.name ?? 'error');
      // What was read stands, and PyPI is asked again in a few minutes, not on every request meanwhile.
      kept = { feed: kept?.feed ?? null, at: now() };
    }
  }
  return async function versions() {
    if (!kept || now() - kept.at >= FRESH_MS) {
      asking ??= ask().finally(() => { asking = null; });
      await asking;
    }
    return kept?.feed ?? null;
  };
}
