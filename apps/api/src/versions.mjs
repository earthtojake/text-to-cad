/**
 * GET /v1/versions: the feed cadgen's daily version check reads (`cadgen/updates.py` in
 * packages/cadgen):
 *
 *   {"latest": "0.9.0"}
 *
 * `latest` is the newest cadgen release PyPI's simple index has a file of that is not yanked: the index uv
 * resolves every pin through, so the feed names a release from the moment it can be installed, and never
 * before. A pre-release is no release here (cadgen reads only `X.Y.Z`), and a release whose every file is
 * yanked is not one either. Only a copy installed by hand reads the feed: a store's copy never checks,
 * since its store updates it.
 *
 * Each instance keeps what it last read for a few minutes, and keeps answering it while PyPI fails. With
 * nothing read yet and PyPI failing, there is no feed (`null`): the handler answers 503, which a released
 * cadgen takes as a check that failed -- silently, keeping the feed it last read, and trying again the next
 * day. `fetch` is handed in, so the tests need no network.
 */

export const INDEX = 'https://pypi.org/simple/cadgen/';
const RELEASE = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/; // cadgen's own `_RELEASE` (updates.py)
const FILE = /^cadgen-([^-]+?)(?:-.+\.whl|\.tar\.gz|\.zip)$/; // a wheel's or an sdist's name, and its version
const TIMEOUT_MS = 3000; // well inside cadgen's own wait (5 s): a PyPI that hangs is a PyPI that failed
const FRESH_MS = 5 * 60 * 1000; // the edge keeps a reply far longer (handler.mjs); this only spares PyPI

const parts = version => version.split('.').map(Number);
const newer = (a, b) => {
  const [x, y] = [parts(a), parts(b)];
  return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
};

/** The newest release an index page (PEP 691 JSON) has an unyanked file of, or `null` when it has none. */
export function latestOf(page) {
  const releases = new Set();
  for (const file of Array.isArray(page?.files) ? page.files : []) {
    const version = FILE.exec(typeof file?.filename === 'string' ? file.filename : '')?.[1];
    if (version && RELEASE.test(version) && !file.yanked) releases.add(version);
  }
  return [...releases].sort(newer).at(-1) ?? null;
}

/**
 * The feed, read from PyPI: a function the handler calls, which answers `{latest}` or `null`, and never
 * throws.
 */
export function pypiVersions({ fetch = globalThis.fetch, now = Date.now, log = console.error, timeout = TIMEOUT_MS } = {}) {
  let kept = null; // { feed, at }
  let asking = null;
  async function ask() {
    try {
      const response = await fetch(INDEX, {
        headers: { accept: 'application/vnd.pypi.simple.v1+json' },
        signal: AbortSignal.timeout(timeout),
      });
      if (!response.ok) throw Object.assign(new Error('PyPI refused'), { code: `pypi_${response.status}` });
      const latest = latestOf(await response.json());
      if (!latest) throw Object.assign(new Error('no release'), { code: 'pypi_no_release' });
      kept = { feed: Object.freeze({ latest }), at: now() };
    } catch (error) {
      log('version feed: PyPI failed:', error?.code ?? error?.name ?? 'error');
      // What was read stands, and PyPI is asked again in a few minutes, not on every request meanwhile.
      if (kept) kept = { ...kept, at: now() };
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

export const versions = pypiVersions();
