/**
 * The version feed, at two addresses, each the same for everyone, both read from one read of PyPI:
 *
 *   GET /v1/releases   {"latest": "1.2.0", "lines": {"0": "0.12.3", "1": "1.2.0"}}
 *   GET /v1/versions   {"latest": "0.11.14"}
 *
 * `/v1/releases` is what cad 0.11.12 and later reads (`cad_server/updates.py` in packages/cad): `latest`, the newest
 * release, and `lines`, the newest release of each major version that has one (its major as a string, the JSON key).
 * `lines` says when: a cad updates itself where `lines` names a newer release of its own major, to PyPI's newest of
 * that major (`uv tool install --upgrade "cad>=X,<N"`); where `lines` names none of its major and `latest` is of a
 * higher major, it runs that bounded upgrade all the same. A higher major never installs itself. The install command
 * installs PyPI's newest, reading no feed.
 *
 * `/v1/versions` is frozen: the releases 0.7.12 to 0.11.11 read it, and nothing newer will. It names the newest
 * release BELOW 0.12.0 (`OLD_BELOW`), in the shape it always had, `{latest}` alone. 0.11.0 to 0.11.11 install by
 * themselves exactly the release it names, but only a patch of their own minor, and 0.10.0 to 0.10.4 install it
 * on a click: naming 0.12.0 or later there would stop every 0.11.x computer updating by itself, while the newest
 * 0.11.x carries the bridge onto the design that updates itself freely (docs/contributing/decisions.md, "Old
 * releases are carried through the newest 0.11"). Until a release 0.12.0 exists, it answers exactly what it did.
 *
 * Every release either address names is the newest that
 *   1. has a file PyPI's simple index lists unyanked (a pre-release is no release here: the server reads only
 *      `X.Y.Z`), read from `cadgen`'s index: a release uploads its projects in steps, `cad`, then `cad-server`
 *      and `cad-mcp` together, then `cadgen`, each only once PyPI lists the step before (.github/workflows/release-publish.yml),
 *      so a release `cadgen` lists can be installed by every name. `cad`'s own index is no use here: it also holds
 *      another owner's yanked 0.8 to 1.1.2 from 2020, and a release half uploaded is listed there first;
 *   2. is at least an hour old by PyPI's own upload time (`upload-time`) of every unyanked file of it: the hour in
 *      which a bad release can be held before any computer installs it. A file with no usable upload time makes
 *      its release not old enough;
 *   3. is not held: `held` is a set of `X.Y.Z` the feed never names, from the Vercel project's `CAD_HELD_RELEASES`
 *      (`heldOf`, README "Holding a release").
 * A release that is held or too new is passed over, never answered as nothing: each address names the newest
 * release that qualifies (and `/v1/versions`, the newest below 0.12.0 that does).
 *
 * Each instance keeps what it last read for a few minutes, and keeps answering it while PyPI fails. With
 * nothing read yet and PyPI failing, there is no feed (`null`): the handler answers 503, which a released
 * server takes as a check that failed -- silently, keeping the feed it last read, and trying again an hour
 * later. `fetch` and `now` are handed in, so the tests need no network and no clock.
 */

export const INDEX = 'https://pypi.org/simple/cadgen/';
export const MIN_AGE_MS = 60 * 60 * 1000; // a release is named an hour after its last file reached PyPI
// `/v1/versions` names nothing at or above it: the releases that read that address install by themselves only a
// patch of their own minor (0.11.x), so the newest 0.11.x is the one they can reach, and it carries them over.
export const OLD_BELOW = '0.12.0';
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
 * The releases an index page (PEP 691 JSON) offers at `now`, oldest first: each with an unyanked file, every
 * unyanked file of it uploaded at least an hour before `now`, and not in `held`.
 */
function readyOf(page, { now = Date.now(), held = new Set() } = {}) {
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
  return ready.map(([version]) => version).sort(newer);
}

/** The pointer an index page gives at `now`: the newest release it offers (`readyOf`); `null` when none is. */
export function latestOf(page, options) {
  return readyOf(page, options).at(-1) ?? null;
}

/**
 * Both addresses' answers from one index page at `now`, `null` when it offers no release at all:
 * `releases`, `{latest, lines}` (`/v1/releases`), and `versions`, `{latest}` naming the newest release below
 * `OLD_BELOW` (`/v1/versions`), or `null` when none below it qualifies.
 */
export function feedsOf(page, options) {
  const ready = readyOf(page, options);
  if (!ready.length) return null;
  const lines = {};
  for (const version of ready) lines[parts(version)[0]] = version; // oldest first: each major ends on its newest
  const old = ready.filter(version => newer(version, OLD_BELOW) < 0).at(-1);
  return {
    releases: Object.freeze({ latest: ready.at(-1), lines: Object.freeze(lines) }),
    versions: old ? Object.freeze({ latest: old }) : null,
  };
}

/**
 * The feed, read from PyPI: two functions the handler calls, `releases` (`{latest, lines}`) and `versions`
 * (`{latest}`), sharing one read of PyPI, each answering its feed or `null`, and never throwing.
 */
export function pypiFeeds({ fetch = globalThis.fetch, now = Date.now, log = console.error, timeout = TIMEOUT_MS, held = new Set() } = {}) {
  let kept = null; // { feeds, at }; a failed first read keeps no feeds until the next attempt
  let asking = null;
  async function ask() {
    try {
      const response = await fetch(INDEX, {
        headers: { accept: 'application/vnd.pypi.simple.v1+json' },
        signal: AbortSignal.timeout(timeout),
      });
      if (!response.ok) throw Object.assign(new Error('PyPI refused'), { code: `pypi_${response.status}` });
      const feeds = feedsOf(await response.json(), { now: now(), held });
      if (!feeds) throw Object.assign(new Error('no release'), { code: 'pypi_no_release' });
      kept = { feeds, at: now() };
    } catch (error) {
      log('version feed: PyPI failed:', error?.code ?? error?.name ?? 'error');
      // What was read stands, and PyPI is asked again in a few minutes, not on every request meanwhile.
      kept = { feeds: kept?.feeds ?? null, at: now() };
    }
  }
  const read = name => async () => {
    if (!kept || now() - kept.at >= FRESH_MS) {
      asking ??= ask().finally(() => { asking = null; });
      await asking;
    }
    return kept?.feeds?.[name] ?? null;
  };
  return { releases: read('releases'), versions: read('versions') };
}
