import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import { parseArgs } from 'node:util';
import { S3mini } from 's3mini';
import { findBlockmaps, findInstallers, findManifests } from './lib/artifacts.ts';
import { RELEASE_DIR, UPDATE_CHANNEL, r2Endpoint, requireEnv } from './lib/config.ts';
import { fail, info, step } from './lib/log.ts';

const { values } = parseArgs({
  options: {
    channel: { type: 'string' },
    prefix: { type: 'string' },
  },
  strict: true,
});

const s3 = new S3mini({
  accessKeyId: requireEnv('R2_ACCESS_KEY_ID'),
  secretAccessKey: requireEnv('R2_SECRET_ACCESS_KEY'),
  endpoint: r2Endpoint(),
  region: 'auto',
});

const resolvedChannel = values.channel ?? UPDATE_CHANNEL;
const manifests = findManifests(resolvedChannel);
if (manifests.length === 0) {
  fail(
    `No update manifests found for channel "${resolvedChannel}" in ${RELEASE_DIR}/. ` +
      `Expected files matching ${resolvedChannel}*.yml — ensure duplicateChannelManifests ran before this step.`
  );
}

const files = [...manifests, ...findInstallers(values.prefix), ...findBlockmaps()];

step(`Uploading ${files.length} artifact(s) to R2`);

for (const file of files) {
  const key = basename(file);
  const contentType = key.endsWith('.yml') ? 'application/yaml' : 'application/octet-stream';
  const data = readFileSync(file);
  info(`Uploading ${key} (${(data.length / 1024 / 1024).toFixed(1)} MB)`);
  await s3.putObject(key, new Uint8Array(data), contentType);
  info(`Uploaded ${key}`);
}

info('All artifacts uploaded to R2');
