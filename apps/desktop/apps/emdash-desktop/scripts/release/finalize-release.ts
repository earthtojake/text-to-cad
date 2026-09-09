import { parseArgs } from 'node:util';
import { Octokit } from '@octokit/rest';
import { fail, info, step, warn } from './lib/log.ts';
import { resolveReleaseVersion } from './lib/version.ts';
import type { ReleaseChannel } from './lib/version.ts';

const { values } = parseArgs({
  options: {
    channel: { type: 'string', default: 'stable' },
  },
  strict: true,
});

const channel = (values.channel ?? 'stable') as ReleaseChannel;
if (!['stable', 'canary'].includes(channel)) {
  fail(`Unknown channel "${channel}"; must be "stable" or "canary"`);
}

const token = process.env.GH_TOKEN;
if (!token) fail('GH_TOKEN env var is required');

const { tag, isCanary } = resolveReleaseVersion(channel);

const octokit = new Octokit({ auth: token });

const OWNER = 'generalaction';
const REPO = 'hardcore';

step(`Looking for draft release with tag ${tag} (channel: ${channel})`);
const { data: releases } = await octokit.rest.repos.listReleases({
  owner: OWNER,
  repo: REPO,
  per_page: 100,
});

const drafts = releases.filter((r) => r.tag_name === tag && r.draft);
if (drafts.length === 0) {
  const summary = releases.map((r) => r.tag_name + '(draft=' + String(r.draft) + ')').join(', ');
  warn(`Available releases: ${summary}`);
  fail(`No draft release found for tag ${tag}`);
}
if (drafts.length > 1) {
  const ids = drafts.map((r) => String(r.id)).join(', ');
  fail(
    `Multiple draft releases found for tag ${tag} (ids: ${ids}); prepare-release should have prevented this. Clean them up before retrying.`
  );
}
const draft = drafts[0];

step(`Publishing release ${tag} (id: ${draft.id}, prerelease: ${isCanary})`);
await octokit.rest.repos.updateRelease({
  owner: OWNER,
  repo: REPO,
  release_id: draft.id,
  draft: false,
  prerelease: isCanary,
});

info(`Release ${tag} is now published on GitHub`);
