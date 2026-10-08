/**
 * GET /v1/versions: the feed cadgen's daily version check reads (`cadgen/updates.py` in
 * packages/cadgen), fixed when the site is built:
 *
 *   {"latest": "0.9.0"}
 *
 * `latest` is this release: the docs app's own version, which the release stamps from VERSION.
 * Publish Release deploys the site after the PyPI upload, so the feed never names a release that
 * cannot be installed yet. Only a copy installed by hand reads it: a store's copy never checks, since
 * its store updates it.
 */
import site from '../../docs/package.json' with { type: 'json' };

export const versions = Object.freeze({ latest: site.version });
