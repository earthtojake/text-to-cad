import { describe, expect, it } from 'vitest';
import {
  artifactArchiveName,
  artifactChecksumContents,
  createDevPackageVersion,
  createArtifactManifest,
  createLauncher,
  nodeDistributionArchiveName,
  nodeDistributionUrl,
  parseAdapterAssetInfos,
  parsePackageArgs,
  parsePackageTarget,
  releaseBuildMatrix,
  releaseMetadataOutput,
  resolveReleaseVersion,
  ripgrepArchiveChecksum,
  ripgrepArchiveName,
  ripgrepDistributionName,
  ripgrepDistributionUrl,
} from './package-helpers';

describe('workspace-server package helpers', () => {
  it('parses and deduplicates supported targets', () => {
    expect(
      parsePackageArgs([
        '--target',
        'linux-x64',
        '--target=darwin-arm64',
        '--target',
        'linux-x64',
        '--verify',
      ])
    ).toEqual({
      targets: [parsePackageTarget('linux-x64'), parsePackageTarget('darwin-arm64')],
      version: undefined,
      verify: true,
      help: false,
    });
  });

  it('parses both explicit package version forms', () => {
    expect(parsePackageArgs(['--version', '1.2.3']).version).toBe('1.2.3');
    expect(parsePackageArgs(['--version=1.2.4-canary.42']).version).toBe('1.2.4-canary.42');
  });

  it('rejects unsupported targets and missing target values', () => {
    expect(() => parsePackageTarget('win32-x64')).toThrow(/Unsupported target/);
    expect(() => parsePackageArgs(['--target'])).toThrow(/requires a value/);
    expect(() => parsePackageArgs(['--version'])).toThrow(/requires a value/);
    expect(() => parsePackageArgs(['--wat'])).toThrow(/Unknown packaging option/);
  });

  it('builds official Node distribution names and URLs', () => {
    const target = parsePackageTarget('linux-arm64');
    expect(nodeDistributionArchiveName('24.14.0', target)).toBe('node-v24.14.0-linux-arm64.tar.xz');
    expect(nodeDistributionUrl('24.14.0', target)).toBe(
      'https://nodejs.org/dist/v24.14.0/node-v24.14.0-linux-arm64.tar.xz'
    );
  });

  it('builds pinned ripgrep release names, URLs, and checksums for each target', () => {
    const linuxArm64 = parsePackageTarget('linux-arm64');
    expect(ripgrepDistributionName(linuxArm64)).toBe('ripgrep-15.2.0-aarch64-unknown-linux-musl');
    expect(ripgrepArchiveName(linuxArm64)).toBe('ripgrep-15.2.0-aarch64-unknown-linux-musl.tar.gz');
    expect(ripgrepDistributionUrl(linuxArm64)).toBe(
      'https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/' +
        'ripgrep-15.2.0-aarch64-unknown-linux-musl.tar.gz'
    );

    for (const targetName of ['darwin-arm64', 'linux-arm64', 'linux-x64']) {
      expect(ripgrepArchiveChecksum(parsePackageTarget(targetName))).toMatch(/^[a-f\d]{64}$/);
    }
  });

  it('builds artifact metadata and archive names', () => {
    const target = parsePackageTarget('darwin-arm64');
    expect(
      createArtifactManifest({
        name: '@emdash/workspace-server',
        version: '0.1.0',
        protocolVersion: '5.0.0',
        nodeVersion: '24.14.0',
        target,
      })
    ).toEqual({
      name: '@emdash/workspace-server',
      version: '0.1.0',
      protocolVersion: '5.0.0',
      os: 'darwin',
      arch: 'arm64',
      nodeVersion: '24.14.0',
      ripgrepVersion: '15.2.0',
    });
    expect(artifactArchiveName('0.1.0', target)).toBe(
      'emdash-workspace-server-0.1.0-darwin-arm64.tar.gz'
    );
  });

  it('derives semver-compatible dev package versions', () => {
    expect(createDevPackageVersion('0.1.0', 'abc123')).toBe('0.1.0-dev.abc123');
    expect(createDevPackageVersion('0.1.0', '0.1.0-dev.manual')).toBe('0.1.0-dev.manual');
    expect(createDevPackageVersion('0.1.0', '0.1.0-dev.abc123.1234567890')).toBe(
      '0.1.0-dev.abc123.1234567890'
    );
    expect(() => createDevPackageVersion('0.1.0', 'not valid')).toThrow(
      /Invalid workspace-server package version/
    );
  });

  it('resolves stable and monotonically newer canary release versions', () => {
    expect(resolveReleaseVersion('stable', '0.1.0', 42)).toBe('0.1.0');
    expect(resolveReleaseVersion('canary', '0.1.0', 42)).toBe('0.1.1-canary.42');
    expect(resolveReleaseVersion('canary', '1.2.3-rc.1', 43)).toBe('1.2.4-canary.43');
    expect(() => resolveReleaseVersion('canary', '0.1.0', 0)).toThrow(/positive safe integer/);
  });

  it('derives the release build matrix from the shared target list', () => {
    expect(releaseBuildMatrix()).toEqual({
      include: [
        { target: 'linux-x64', runner: 'ubuntu-latest' },
        { target: 'linux-arm64', runner: 'ubuntu-24.04-arm' },
        { target: 'darwin-arm64', runner: 'macos-latest' },
      ],
    });
  });

  it('prints one-line GitHub release metadata outputs', () => {
    expect(releaseMetadataOutput('canary', '0.1.0', 42)).toBe(
      [
        'version=0.1.1-canary.42',
        'matrix={"include":[{"target":"linux-x64","runner":"ubuntu-latest"},{"target":"linux-arm64","runner":"ubuntu-24.04-arm"},{"target":"darwin-arm64","runner":"macos-latest"}]}',
        'probeArtifact=emdash-workspace-server-0.1.1-canary.42-linux-x64.tar.gz',
        '',
      ].join('\n')
    );
  });

  it('formats sha256 sidecars for remote verification', () => {
    const checksum = 'a'.repeat(64);
    expect(artifactChecksumContents(checksum, 'server.tar.gz')).toBe(
      `${checksum}  server.tar.gz\n`
    );
    expect(() => artifactChecksumContents('not-a-checksum', 'server.tar.gz')).toThrow('sha256');
  });

  it('generates a relocatable launcher with a safely quoted app version', () => {
    const launcher = createLauncher("0.1.0-canary'1");
    expect(launcher).toContain('script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)');
    expect(launcher).toContain("export EMDASH_WS_APP_VERSION='0.1.0-canary'\\''1'");
    expect(launcher).toContain('export EMDASH_WS_RIPGREP_PATH="$root_dir/bin/rg"');
    expect(launcher).toContain('exec "$root_dir/node" "$root_dir/dist/index.mjs" "$@"');
    expect(launcher.endsWith('\n')).toBe(true);
  });

  it('parses adapter assets from the built plugins manifest', () => {
    expect(
      parseAdapterAssetInfos([
        { name: 'claude-acp', format: 'esm', specifier: '@agentclientprotocol/claude-agent-acp' },
        { name: 'codex-acp', format: 'cjs', external: ['@openai/codex'] },
      ])
    ).toEqual([
      { name: 'claude-acp', format: 'esm' },
      { name: 'codex-acp', format: 'cjs' },
    ]);

    expect(() => parseAdapterAssetInfos({})).toThrow(/adapterAssets array/);
    expect(() => parseAdapterAssetInfos([{ name: 'bad', format: 'iife' }])).toThrow(
      /invalid adapter asset/
    );
  });
});
