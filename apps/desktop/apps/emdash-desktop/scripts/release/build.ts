import { cpSync, mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { basename, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { Octokit } from '@octokit/rest';
import { Arch, Platform, build as electronBuild } from 'electron-builder';
import type { Configuration } from 'electron-builder';
import canaryConfig from '../../electron-builder.canary.config.ts';
import stableConfig from '../../electron-builder.config.ts';
import { duplicateChannelManifests, resolvePublishChannels } from './lib/artifacts.ts';
import { GITHUB_OWNER, GITHUB_REPO } from './lib/config.ts';
import { exec } from './lib/exec.ts';
import { fail, info, step, warn } from './lib/log.ts';
import { resolveReleaseVersion } from './lib/version.ts';
import type { ReleaseChannel } from './lib/version.ts';

const { values } = parseArgs({
  options: {
    platform: { type: 'string' },
    arch: { type: 'string', default: 'both' },
    targets: { type: 'string' },
    config: { type: 'string', default: 'electron-builder.config.ts' },
    channel: { type: 'string', default: 'stable' },
  },
  strict: true,
});

const platform = values.platform;
if (!platform || !['mac', 'linux', 'win'].includes(platform)) {
  fail(
    'Usage: build.ts --platform mac|linux|win [--arch arm64|x64|both] [--targets dmg,zip] [--config electron-builder.config.ts] [--channel stable|canary]'
  );
}

const channel = (values.channel ?? 'stable') as ReleaseChannel;
if (!['stable', 'canary'].includes(channel)) {
  fail(`Unknown channel "${channel}"; must be "stable" or "canary"`);
}

const archInput = values.arch ?? 'both';
const archs: string[] = archInput === 'both' ? ['x64', 'arm64'] : [archInput];

const defaultTargets: Record<string, string[]> = {
  mac: ['dmg', 'zip'],
  linux: ['AppImage', 'deb', 'rpm'],
  win: ['nsis', 'msi'],
};
const targetList = values.targets ? values.targets.split(',') : defaultTargets[platform];

const platformMap: Record<string, Platform> = {
  mac: Platform.MAC,
  linux: Platform.LINUX,
  win: Platform.WINDOWS,
};

const archMap: Record<string, Arch> = {
  x64: Arch.x64,
  arm64: Arch.arm64,
};

const ebPlatform = platformMap[platform];

const { version: overrideVersion, tag, isCanary } = resolveReleaseVersion(channel);
if (isCanary) {
  info(`Canary build: packaging as version ${overrideVersion} (tag ${tag})`);
}

step('Creating deployment directory with production dependencies');
const workspaceRoot = resolve(process.cwd(), '../..');
const deployDir = mkdtempSync(join(workspaceRoot, '.emdash-deploy-'));
exec(`pnpm --filter @hardcore/desktop deploy --legacy --prod ${deployDir}`, {
  cwd: workspaceRoot,
  echo: true,
});

step('Copying built assets into deployment directory');
cpSync('out', join(deployDir, 'out'), { recursive: true });
cpSync('drizzle', join(deployDir, 'drizzle'), { recursive: true });

const electronVersion = exec(`node -p "require('electron/package.json').version"`);

const configName = basename(values.config ?? 'electron-builder.config.ts');
const baseConfig: Configuration =
  configName === 'electron-builder.config.ts'
    ? stableConfig
    : configName === 'electron-builder.canary.config.ts'
      ? canaryConfig
      : fail(`Unknown electron-builder config "${configName}"`);

try {
  for (const arch of archs) {
    step(`Building ${platform} ${targetList.join(' ')} for ${arch}`);

    exec(
      `node --experimental-strip-types scripts/release/rebuild-native.ts --arch ${arch} --deploy-dir ${deployDir}`,
      { echo: true }
    );

    const archEnum = archMap[arch];
    if (!archEnum) fail(`Unknown arch: ${arch}`);

    const buildTargets = ebPlatform.createTarget(targetList, archEnum);
    // Clone per iteration: electron-builder's normalizeFiles mutates config.files in
    // place (collapsing strings into a single fileset and leaving null holes), which
    // crashes the second arch iteration if the same config object is reused.
    const { beforePack, afterPack, ...cloneableConfig } = baseConfig;
    const config: Configuration = {
      ...structuredClone(cloneableConfig),
      ...(beforePack ? { beforePack } : {}),
      ...(afterPack ? { afterPack } : {}),
      electronVersion,
      npmRebuild: false,
      ...(isCanary ? { extraMetadata: { version: overrideVersion } } : {}),
    };

    await electronBuild({
      targets: buildTargets,
      config,
      projectDir: deployDir,
      publish: 'always',
    });

    info(`Built ${platform} ${targetList.join(' ')} for ${arch}`);
  }

  step('Copying release artifacts to app directory');
  cpSync(join(deployDir, 'release'), 'release', { recursive: true });

  step('Duplicating manifests for R2 stable channel');
  const publishArray = Array.isArray(baseConfig.publish)
    ? baseConfig.publish
    : baseConfig.publish
      ? [baseConfig.publish]
      : [];
  const { githubChannel, r2Channel } = resolvePublishChannels(
    publishArray as Array<Record<string, unknown>>
  );

  if (r2Channel && githubChannel !== r2Channel) {
    const duplicated = duplicateChannelManifests(githubChannel, r2Channel);
    if (duplicated.length > 0) {
      info(`Duplicated ${duplicated.length} manifest(s): "${githubChannel}" → "${r2Channel}"`);
      const ghToken = process.env.GH_TOKEN;
      if (ghToken) {
        await uploadManifestsToGithubDraft(duplicated, tag, ghToken);
      } else {
        info(
          'GH_TOKEN not set; skipping GitHub manifest upload (R2 upload will still include them)'
        );
      }
    } else {
      warn(`No "${githubChannel}" manifests found to duplicate for R2 channel "${r2Channel}"`);
    }
  }
} finally {
  rmSync(deployDir, { recursive: true, force: true });
}

/**
 * Uploads the given manifest files to the GitHub draft release for `tag`, clobbering
 * any asset of the same name that already exists (safe for re-runs).
 */
async function uploadManifestsToGithubDraft(
  files: string[],
  tag: string,
  token: string
): Promise<void> {
  const octokit = new Octokit({ auth: token });

  const { data: releases } = await octokit.rest.repos.listReleases({
    owner: GITHUB_OWNER,
    repo: GITHUB_REPO,
    per_page: 100,
  });
  const drafts = releases.filter((r) => r.tag_name === tag && r.draft);
  if (drafts.length === 0) {
    warn(`No draft release found for tag ${tag}; skipping GitHub manifest upload`);
    return;
  }
  if (drafts.length > 1) {
    const ids = drafts.map((r) => String(r.id)).join(', ');
    fail(
      `Multiple draft releases found for tag ${tag} (ids: ${ids}); cannot safely upload manifests. Run prepare-release.ts to fix.`
    );
  }
  const draft = drafts[0];

  const { data: assets } = await octokit.rest.repos.listReleaseAssets({
    owner: GITHUB_OWNER,
    repo: GITHUB_REPO,
    release_id: draft.id,
    per_page: 100,
  });

  step(`Uploading ${files.length} R2 channel manifest(s) to GitHub draft release ${tag}`);
  for (const file of files) {
    const name = basename(file);
    const existing = assets.find((a) => a.name === name);
    if (existing) {
      await octokit.rest.repos.deleteReleaseAsset({
        owner: GITHUB_OWNER,
        repo: GITHUB_REPO,
        asset_id: existing.id,
      });
    }
    await octokit.rest.repos.uploadReleaseAsset({
      owner: GITHUB_OWNER,
      repo: GITHUB_REPO,
      release_id: draft.id,
      name,
      data: readFileSync(file, 'utf-8'),
      headers: {
        'content-type': 'application/yaml',
        'content-length': statSync(file).size,
      },
    });
    info(`Uploaded ${name} to draft release ${tag}`);
  }
}
