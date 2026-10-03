/**
 * GET /v1/versions: the feed cadgen's daily version check reads (`cadgen/updates.py` in
 * packages/cadgen), fixed when the site is built:
 *
 *   {"latest": "0.9.0", "minimum": {"claude-directory": "0.8.2"}}
 *
 * `latest` is this release: the docs app's own version, which the release stamps from VERSION.
 * Publish Release deploys the site after the PyPI upload, so the feed never names a release that
 * cannot be installed yet. `minimum` (`minimum.json`) is, per store, the oldest release that
 * store's copies may run before cadgen tells them to install by hand; a store with none is never
 * told, since its store updates it. Raising one is an edit to that file and a run of Deploy Docs.
 */
import site from '../../../package.json' with { type: 'json' };
import minimum from './minimum.json' with { type: 'json' };

export const STORES = ['claude-directory', 'openai-directory', 'cursor-marketplace'];

export const versions = Object.freeze({ latest: site.version, minimum });
