export const artifactRootName = 'emdash-workspace-server';
export const RIPGREP_VERSION = '15.2.0';

const targetDefinitions = {
  'darwin-arm64': {
    id: 'darwin-arm64',
    os: 'darwin',
    arch: 'arm64',
    dockerPlatform: undefined,
  },
  'linux-arm64': {
    id: 'linux-arm64',
    os: 'linux',
    arch: 'arm64',
    dockerPlatform: 'linux/arm64',
  },
  'linux-x64': {
    id: 'linux-x64',
    os: 'linux',
    arch: 'x64',
    dockerPlatform: 'linux/amd64',
  },
} as const;

export type PackageTargetId = keyof typeof targetDefinitions;
export type PackageTarget = (typeof targetDefinitions)[PackageTargetId];
export type ReleaseChannel = 'stable' | 'canary';

const releaseRunners: Record<PackageTargetId, string> = {
  'darwin-arm64': 'macos-latest',
  'linux-arm64': 'ubuntu-24.04-arm',
  'linux-x64': 'ubuntu-latest',
};

export const releaseTargets = [
  targetDefinitions['linux-x64'],
  targetDefinitions['linux-arm64'],
  targetDefinitions['darwin-arm64'],
] as const satisfies readonly PackageTarget[];

const ripgrepReleaseTargets: Record<
  PackageTargetId,
  Readonly<{ triple: string; sha256: string }>
> = {
  'darwin-arm64': {
    triple: 'aarch64-apple-darwin',
    sha256: '3750b2e93f37e0c692657da574d7019a101c0084da05a790c83fd335bad973e4',
  },
  'linux-arm64': {
    triple: 'aarch64-unknown-linux-musl',
    sha256: '800b1e7206afe799dfb5a6901f23147cfaabe0e52210538100f61e86e1740915',
  },
  'linux-x64': {
    triple: 'x86_64-unknown-linux-musl',
    sha256: '33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c',
  },
};

export type PackageCliOptions = {
  targets: PackageTarget[];
  version?: string;
  verify: boolean;
  help: boolean;
};

export type WorkspaceServerArtifactManifest = {
  name: string;
  version: string;
  protocolVersion: string;
  os: PackageTarget['os'];
  arch: PackageTarget['arch'];
  nodeVersion: string;
  ripgrepVersion: string;
};

export type PackageAdapterAssetInfo = {
  name: string;
  format: 'esm' | 'cjs';
};

const workspaceServerVersionPattern =
  /^\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$/;

export function parsePackageTarget(value: string): PackageTarget {
  if (value in targetDefinitions) {
    return targetDefinitions[value as PackageTargetId];
  }
  throw new Error(
    `Unsupported target '${value}'. Expected one of: ${Object.keys(targetDefinitions).join(', ')}`
  );
}

export function parsePackageArgs(args: string[]): PackageCliOptions {
  const targets: PackageTarget[] = [];
  let version: string | undefined;
  let verify = false;
  let help = false;

  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === '--verify') {
      verify = true;
      continue;
    }
    if (argument === '--help' || argument === '-h') {
      help = true;
      continue;
    }
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
    throw new Error(`Unknown packaging option '${argument}'`);
  }

  return {
    targets: targets.filter(
      (target, index) => targets.findIndex((candidate) => candidate.id === target.id) === index
    ),
    version,
    verify,
    help,
  };
}

export function nodeDistributionArchiveName(nodeVersion: string, target: PackageTarget): string {
  return `node-v${nodeVersion}-${target.os}-${target.arch}.tar.xz`;
}

export function nodeDistributionUrl(nodeVersion: string, target: PackageTarget): string {
  return `https://nodejs.org/dist/v${nodeVersion}/${nodeDistributionArchiveName(
    nodeVersion,
    target
  )}`;
}

export function ripgrepDistributionName(target: PackageTarget): string {
  return `ripgrep-${RIPGREP_VERSION}-${ripgrepReleaseTargets[target.id].triple}`;
}

export function ripgrepArchiveName(target: PackageTarget): string {
  return `${ripgrepDistributionName(target)}.tar.gz`;
}

export function ripgrepDistributionUrl(target: PackageTarget): string {
  return `https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/${ripgrepArchiveName(
    target
  )}`;
}

export function ripgrepArchiveChecksum(target: PackageTarget): string {
  return ripgrepReleaseTargets[target.id].sha256;
}

export function artifactArchiveName(version: string, target: PackageTarget): string {
  return `${artifactRootName}-${version}-${target.os}-${target.arch}.tar.gz`;
}

export function releaseBuildMatrix(): {
  include: { target: string; runner: string }[];
} {
  return {
    include: releaseTargets.map((target) => ({
      target: target.id,
      runner: releaseRunners[target.id],
    })),
  };
}

export function createDevPackageVersion(baseVersion: string, identifier: string): string {
  validatePackageVersion(baseVersion);
  const normalizedIdentifier = identifier.trim();
  if (normalizedIdentifier.length === 0) {
    throw new Error('Dev package version identifier cannot be empty');
  }
  if (workspaceServerVersionPattern.test(normalizedIdentifier)) {
    return normalizedIdentifier;
  }
  const version = `${baseVersion}-dev.${normalizedIdentifier}`;
  validatePackageVersion(version);
  return version;
}

export function resolveReleaseVersion(
  channel: ReleaseChannel,
  baseVersion: string,
  runNumber: number
): string {
  validatePackageVersion(baseVersion);
  if (channel === 'stable') return baseVersion;
  if (!Number.isSafeInteger(runNumber) || runNumber <= 0) {
    throw new Error('Canary run number must be a positive safe integer');
  }

  const base = baseVersion.split('-')[0];
  const parts = base?.split('.').map(Number);
  if (parts === undefined || parts.length !== 3 || parts.some(Number.isNaN)) {
    throw new Error(`Cannot parse workspace-server version '${baseVersion}' as major.minor.patch`);
  }
  const [major, minor, patch] = parts;
  if (major === undefined || minor === undefined || patch === undefined) {
    throw new Error(`Cannot parse workspace-server version '${baseVersion}' as major.minor.patch`);
  }
  return validatePackageVersion(`${major}.${minor}.${patch + 1}-canary.${runNumber}`);
}

export function releaseMetadataOutput(
  channel: ReleaseChannel,
  baseVersion: string,
  runNumber: number
): string {
  const version = resolveReleaseVersion(channel, baseVersion, runNumber);
  return [
    `version=${version}`,
    `matrix=${JSON.stringify(releaseBuildMatrix())}`,
    `probeArtifact=${artifactArchiveName(version, releaseTargets[0])}`,
    '',
  ].join('\n');
}

export function validatePackageVersion(version: string): string {
  if (!workspaceServerVersionPattern.test(version)) {
    throw new Error(`Invalid workspace-server package version '${version}'`);
  }
  return version;
}

export function artifactChecksumContents(checksum: string, archiveName: string): string {
  if (!/^[a-f\d]{64}$/.test(checksum)) throw new Error('Artifact checksum must be sha256 hex');
  if (archiveName.length === 0 || /[\s/\\]/.test(archiveName)) {
    throw new Error('Artifact archive name must be a single non-empty path component');
  }
  return `${checksum}  ${archiveName}\n`;
}

export function createArtifactManifest(options: {
  name: string;
  version: string;
  protocolVersion: string;
  nodeVersion: string;
  target: PackageTarget;
}): WorkspaceServerArtifactManifest {
  return {
    name: options.name,
    version: options.version,
    protocolVersion: options.protocolVersion,
    os: options.target.os,
    arch: options.target.arch,
    nodeVersion: options.nodeVersion,
    ripgrepVersion: RIPGREP_VERSION,
  };
}

export function parseAdapterAssetInfos(value: unknown): PackageAdapterAssetInfo[] {
  if (!Array.isArray(value)) {
    throw new Error('@emdash/plugins adapter manifest did not export an adapterAssets array');
  }

  return value.map((asset) => {
    if (
      !isRecord(asset) ||
      typeof asset['name'] !== 'string' ||
      (asset['format'] !== 'esm' && asset['format'] !== 'cjs')
    ) {
      throw new Error('@emdash/plugins adapter manifest contains an invalid adapter asset');
    }
    return { name: asset['name'], format: asset['format'] };
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function createLauncher(version: string): string {
  return `#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

export EMDASH_WS_APP_VERSION=${quoteShellArgument(version)}
export EMDASH_WS_RIPGREP_PATH="$root_dir/bin/rg"
exec "$root_dir/node" "$root_dir/dist/index.mjs" "$@"
`;
}

function quoteShellArgument(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}
