import {
  channelPointerPath,
  releaseChannelSchema,
  releaseVersionSchema,
  type ChannelPointer,
  type ReleaseChannel,
} from '@emdash/core/workspace-server';
import {
  artifactArchiveName,
  artifactRootName,
  parsePackageTarget,
  releaseTargets,
  type PackageTarget,
} from './package-helpers';

export const workspaceServerObjectPrefix = 'workspace-server';

const mutableCacheControl = 'no-cache';
const immutableCacheControl = 'public, max-age=31536000, immutable';

const sha256Pattern = /^[a-f\d]{64}$/;

export type ImmutableUploadDecision = 'skip' | 'upload';

export type UploadOptions = {
  version?: string;
  targets?: PackageTarget[];
  channels: ReleaseChannel[];
};

export function parseUploadArgs(args: string[]): UploadOptions {
  const targets: PackageTarget[] = [];
  const channels: ReleaseChannel[] = [];
  let version: string | undefined;

  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === '--target') {
      const value = args[index + 1];
      if (value === undefined) throw new Error('--target requires a value');
      targets.push(parsePackageTarget(value));
      index += 1;
      continue;
    }
    if (argument.startsWith('--target=')) {
      targets.push(parsePackageTarget(argument.slice('--target='.length)));
      continue;
    }
    if (argument === '--channel') {
      const value = args[index + 1];
      if (value === undefined) throw new Error('--channel requires a value');
      channels.push(parseReleaseChannel(value));
      index += 1;
      continue;
    }
    if (argument.startsWith('--channel=')) {
      channels.push(parseReleaseChannel(argument.slice('--channel='.length)));
      continue;
    }
    if (argument === '--version') {
      const value = args[index + 1];
      if (value === undefined) throw new Error('--version requires a value');
      version = value;
      index += 1;
      continue;
    }
    if (argument.startsWith('--version=')) {
      version = argument.slice('--version='.length);
      continue;
    }
    throw new Error(`Unknown upload option '${argument}'`);
  }

  return {
    version,
    targets:
      targets.length === 0
        ? undefined
        : targets.filter(
            (target, index) =>
              targets.findIndex((candidate) => candidate.id === target.id) === index
          ),
    channels:
      channels.length === 0
        ? ['stable']
        : channels.filter((channel, index) => channels.indexOf(channel) === index),
  };
}

export function expectedArtifactNames(
  version: string,
  targets: readonly PackageTarget[] = releaseTargets
): string[] {
  validateReleaseVersion(version);
  return targets.flatMap((target) => {
    const archiveName = artifactArchiveName(version, target);
    return [archiveName, `${archiveName}.sha256`];
  });
}

export function artifactVersionFromArchiveName(
  archiveName: string,
  target: PackageTarget
): string | undefined {
  const prefix = `${artifactRootName}-`;
  const suffix = `-${target.os}-${target.arch}.tar.gz`;
  if (!archiveName.startsWith(prefix) || !archiveName.endsWith(suffix)) return undefined;
  const version = archiveName.slice(prefix.length, -suffix.length);
  validateReleaseVersion(version);
  return version;
}

export function versionedArtifactObjectKey(version: string, artifactName: string): string {
  validateReleaseVersion(version);
  if (artifactName.length === 0 || /[/\\]/.test(artifactName)) {
    throw new Error('Artifact name must be a single non-empty path component');
  }
  return `${workspaceServerObjectPrefix}/${version}/${artifactName}`;
}

export function versionedInstallScriptObjectKey(version: string): string {
  return versionedArtifactObjectKey(version, 'install.sh');
}

export function channelPointerObjectKey(channel: ReleaseChannel, major: number): string {
  return `${workspaceServerObjectPrefix}/${channelPointerPath(channel, major)}`;
}

export function channelPointerUrl(baseUrl: string, channel: ReleaseChannel, major: number): string {
  const normalizedBaseUrl = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
  return new URL(channelPointerObjectKey(channel, major), normalizedBaseUrl).toString();
}

export function mutableReleaseObjectKeys(
  channels: readonly ReleaseChannel[],
  major: number
): string[] {
  return channels.map((channel) => channelPointerObjectKey(channel, major));
}

export function contentTypeForObjectKey(key: string): string {
  if (key.endsWith('.sh')) return 'text/x-shellscript';
  if (key.endsWith('.json')) return 'application/json';
  if (key.endsWith('.txt') || key.endsWith('.sha256')) return 'text/plain';
  return 'application/octet-stream';
}

export function cacheControlForObjectKey(key: string): string {
  if (key.startsWith(`${workspaceServerObjectPrefix}/channels/`)) {
    return mutableCacheControl;
  }

  const relativeKey = key.startsWith(`${workspaceServerObjectPrefix}/`)
    ? key.slice(workspaceServerObjectPrefix.length + 1)
    : '';
  const separatorIndex = relativeKey.indexOf('/');
  if (separatorIndex <= 0 || separatorIndex === relativeKey.length - 1) {
    throw new Error(`Unknown workspace-server release object key '${key}'`);
  }
  validateReleaseVersion(relativeKey.slice(0, separatorIndex));
  return immutableCacheControl;
}

export function assertPointerVersionPublishedInRun(
  pointer: ChannelPointer,
  publishedVersions: ReadonlySet<string>
): void {
  if (!publishedVersions.has(pointer.artifactVersion)) {
    throw new Error(
      `Refusing to publish channel pointer for workspace-server ${pointer.artifactVersion}: version was not published in this run`
    );
  }
}

export function parseArtifactChecksum(contents: string, expectedArchiveName: string): string {
  const match = /^([a-fA-F\d]{64})  \*?([^\s]+)\r?\n?$/.exec(contents);
  if (match === null || match[1] === undefined || match[2] !== expectedArchiveName) {
    throw new Error(`Invalid checksum sidecar for ${expectedArchiveName}`);
  }
  return match[1].toLowerCase();
}

export function immutableUploadDecision(
  localSha256: string,
  remoteSha256?: string
): ImmutableUploadDecision {
  validateSha256(localSha256);
  if (remoteSha256 === undefined) return 'upload';
  validateSha256(remoteSha256);
  if (remoteSha256 === localSha256) return 'skip';
  throw new Error(
    `Refusing to replace immutable object: local sha256 ${localSha256}, remote sha256 ${remoteSha256}`
  );
}

export function validateReleaseVersion(version: string): void {
  if (!releaseVersionSchema.safeParse(version).success) {
    throw new Error(`Invalid workspace-server release version '${version}'`);
  }
}

function parseReleaseChannel(value: string): ReleaseChannel {
  const parsed = releaseChannelSchema.safeParse(value);
  if (!parsed.success) {
    throw new Error(`Invalid workspace-server release channel '${value}'`);
  }
  return parsed.data;
}

function validateSha256(checksum: string): void {
  if (!sha256Pattern.test(checksum)) {
    throw new Error(`Invalid sha256 checksum '${checksum}'`);
  }
}
