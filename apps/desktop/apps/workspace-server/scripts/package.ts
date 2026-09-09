import { spawn, type StdioOptions } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import {
  chmod,
  copyFile,
  cp,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises';
import { builtinModules } from 'node:module';
import { homedir, tmpdir } from 'node:os';
import { basename, dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import {
  artifactArchiveName,
  artifactChecksumContents,
  artifactRootName,
  createDevPackageVersion,
  createArtifactManifest,
  createLauncher,
  nodeDistributionArchiveName,
  nodeDistributionUrl,
  parseAdapterAssetInfos,
  parsePackageArgs,
  ripgrepArchiveChecksum,
  ripgrepArchiveName,
  ripgrepDistributionName,
  ripgrepDistributionUrl,
  RIPGREP_VERSION,
  validatePackageVersion,
  type PackageTarget,
  type PackageAdapterAssetInfo,
} from './package-helpers.ts';

const nativePackages = ['@parcel/watcher', 'better-sqlite3', 'node-pty'] as const;
const expectedEntryBundleNames = [
  'acp-runtime.mjs',
  'agent-config-runtime.mjs',
  'automations-runtime.mjs',
  'file-search-runtime.mjs',
  'files-runtime.mjs',
  'fs-watch-runtime.mjs',
  'git-runtime.mjs',
  'index.mjs',
  'terminals-runtime.mjs',
  'tui-agents-runtime.mjs',
] as const;
const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const appDirectory = resolve(scriptDirectory, '..');
const repositoryDirectory = resolve(appDirectory, '../..');
const runtimeDepsDirectory = join(appDirectory, 'runtime-deps');
const dockerfilePath = join(appDirectory, 'tooling/docker/runtime-deps.dockerfile');
const artifactsDirectory = join(appDirectory, 'dist-artifacts');

type PackageMetadata = {
  name: string;
  version: string;
  devBuild: boolean;
};

type AdapterValidationModule = {
  validateAdapterBundleAssets: (options: {
    adapterDirectory: string;
    assets: readonly PackageAdapterAssetInfo[];
  }) => Promise<void>;
};

async function main(): Promise<void> {
  const options = parsePackageArgs(process.argv.slice(2));
  if (options.help) {
    printUsage();
    return;
  }
  if (options.targets.length === 0) {
    throw new Error('At least one --target is required');
  }

  validateTargetHosts(options.targets);

  const packageMetadata = await readPackageMetadata(options.version);
  process.stdout.write(`Workspace-server package version: ${packageMetadata.version}\n`);
  const nodeVersion = (await readFile(join(repositoryDirectory, '.nvmrc'), 'utf8')).trim();
  if (!/^\d+\.\d+\.\d+$/.test(nodeVersion)) {
    throw new Error(`Expected .nvmrc to contain a full Node version, received '${nodeVersion}'`);
  }

  process.stdout.write('Building workspace-server package dependencies...\n');
  for (const packageName of ['@emdash/shared', '@emdash/wire', '@emdash/core']) {
    await runCommand('pnpm', ['--filter', packageName, 'run', 'build'], {
      cwd: repositoryDirectory,
    });
  }
  const protocolVersion = await readProtocolVersion();

  process.stdout.write('Building plugin adapter assets...\n');
  await runCommand('pnpm', ['--filter', '@emdash/plugins', 'run', 'build'], {
    cwd: repositoryDirectory,
  });
  const adapterAssets = await readBuiltAdapterAssets();

  process.stdout.write('Building platform-independent workspace-server bundles...\n');
  await runCommand('pnpm', ['run', 'build'], { cwd: appDirectory });
  const bundleNames = await inspectBundles();

  await mkdir(artifactsDirectory, { recursive: true });
  for (const target of options.targets) {
    await packageTarget({
      target,
      packageMetadata,
      protocolVersion,
      nodeVersion,
      bundleNames,
      adapterAssets,
      verify: options.verify,
    });
  }
}

async function packageTarget(options: {
  target: PackageTarget;
  packageMetadata: PackageMetadata;
  protocolVersion: string;
  nodeVersion: string;
  bundleNames: string[];
  adapterAssets: readonly PackageAdapterAssetInfo[];
  verify: boolean;
}): Promise<void> {
  const {
    target,
    packageMetadata,
    protocolVersion,
    nodeVersion,
    bundleNames,
    adapterAssets,
    verify,
  } = options;
  const temporaryDirectory = await mkdtemp(join(tmpdir(), `emdash-ws-package-${target.id}-`));

  try {
    process.stdout.write(`Packaging ${target.id}...\n`);
    const [nodeDistributionDirectory, ripgrepDistributionDirectory] = await Promise.all([
      extractNodeDistribution(nodeVersion, target, temporaryDirectory),
      extractRipgrepDistribution(target, temporaryDirectory),
    ]);
    const runtimeNodeModules =
      target.os === 'darwin'
        ? await installDarwinRuntimeDependencies(nodeDistributionDirectory, temporaryDirectory)
        : await buildLinuxRuntimeDependencies(nodeVersion, target, temporaryDirectory);
    const artifactDirectory = await assembleArtifact({
      target,
      packageMetadata,
      protocolVersion,
      nodeVersion,
      nodeDistributionDirectory,
      runtimeNodeModules,
      ripgrepDistributionDirectory,
      bundleNames,
      adapterAssets,
      temporaryDirectory,
    });
    const archivePath = join(
      artifactsDirectory,
      artifactArchiveName(packageMetadata.version, target)
    );

    await runCommand('tar', ['-czf', archivePath, artifactRootName], {
      cwd: dirname(artifactDirectory),
      env: { ...process.env, COPYFILE_DISABLE: '1' },
    });
    const archiveChecksum = await sha256File(archivePath);
    await writeFile(
      `${archivePath}.sha256`,
      artifactChecksumContents(archiveChecksum, basename(archivePath)),
      'utf8'
    );
    process.stdout.write(`Created ${archivePath}\n`);
    process.stdout.write(`Created ${archivePath}.sha256\n`);

    if (verify) {
      process.stdout.write(`Smoke-verifying ${target.id} artifact...\n`);
      await verifyArtifact(archivePath, target);
      process.stdout.write(`Verified ${target.id} artifact\n`);
    }
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

async function readPackageMetadata(explicitVersion?: string): Promise<PackageMetadata> {
  const raw: unknown = JSON.parse(await readFile(join(appDirectory, 'package.json'), 'utf8'));
  if (!isRecord(raw) || typeof raw['name'] !== 'string' || typeof raw['version'] !== 'string') {
    throw new Error('workspace-server package.json must contain string name and version fields');
  }
  const version = await resolvePackageVersion(raw['version'], explicitVersion);
  return { name: raw['name'], version: version.value, devBuild: version.devBuild };
}

async function resolvePackageVersion(
  baseVersion: string,
  explicitVersion?: string
): Promise<{ value: string; devBuild: boolean }> {
  if (explicitVersion !== undefined) {
    if (
      process.env['EMDASH_WS_DEV_BUILD'] === '1' ||
      process.env['EMDASH_WS_DEV_VERSION'] !== undefined
    ) {
      throw new Error(
        '--version cannot be combined with EMDASH_WS_DEV_BUILD or EMDASH_WS_DEV_VERSION'
      );
    }
    return { value: validatePackageVersion(explicitVersion), devBuild: false };
  }

  const explicitDevVersion = process.env['EMDASH_WS_DEV_VERSION']?.trim();
  if (explicitDevVersion !== undefined && explicitDevVersion.length > 0) {
    return { value: createDevPackageVersion(baseVersion, explicitDevVersion), devBuild: true };
  }
  if (process.env['EMDASH_WS_DEV_BUILD'] !== '1') {
    return { value: baseVersion, devBuild: false };
  }
  return {
    value: createDevPackageVersion(baseVersion, await devBuildIdentifier()),
    devBuild: true,
  };
}

async function devBuildIdentifier(): Promise<string> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  try {
    const sha = (
      await runCommandOutput('git', ['rev-parse', '--short', 'HEAD'], {
        cwd: repositoryDirectory,
      })
    ).trim();
    if (/^[0-9A-Za-z]+$/.test(sha)) return `${sha}.${timestamp}`;
  } catch {
    // Fall back below when this source tree is not a git checkout.
  }
  return timestamp;
}

async function readProtocolVersion(): Promise<string> {
  const workspaceServerModule: unknown = await import('@emdash/core/workspace-server');
  if (
    !isRecord(workspaceServerModule) ||
    typeof workspaceServerModule['PROTOCOL_VERSION'] !== 'string'
  ) {
    throw new Error('@emdash/core/workspace-server must export a string PROTOCOL_VERSION');
  }
  return workspaceServerModule['PROTOCOL_VERSION'];
}

async function readBuiltAdapterAssets(): Promise<readonly PackageAdapterAssetInfo[]> {
  const manifestPath = join(
    repositoryDirectory,
    'packages/plugins/dist/agents/adapter-manifest.mjs'
  );
  const manifestModule: unknown = await import(pathToFileURL(manifestPath).href);
  if (!isRecord(manifestModule)) {
    throw new Error('@emdash/plugins adapter manifest did not export adapterAssets');
  }

  return parseAdapterAssetInfos(manifestModule['adapterAssets']);
}

async function validateBuiltAdapterDirectory(
  adapterDirectory: string,
  assets: readonly PackageAdapterAssetInfo[]
): Promise<void> {
  const validationPath = join(
    repositoryDirectory,
    'packages/plugins/dist/agents/helpers/adapter-validation.mjs'
  );
  const validationModule: unknown = await import(pathToFileURL(validationPath).href);
  if (
    !isRecord(validationModule) ||
    typeof validationModule['validateAdapterBundleAssets'] !== 'function'
  ) {
    throw new Error('@emdash/plugins adapter validation helper was not built');
  }
  const { validateAdapterBundleAssets } = validationModule as AdapterValidationModule;
  await validateAdapterBundleAssets({ adapterDirectory, assets });
}

function validateTargetHosts(targets: PackageTarget[]): void {
  for (const target of targets) {
    if (target.os === 'darwin' && (process.platform !== 'darwin' || process.arch !== target.arch)) {
      throw new Error(
        `${target.id} native dependencies must be packaged on a ${target.id} host; ` +
          `current host is ${process.platform}-${process.arch}`
      );
    }
  }
}

async function inspectBundles(): Promise<string[]> {
  const distDirectory = join(appDirectory, 'dist');
  const entries = await readdir(distDirectory, { withFileTypes: true });
  const bundleNames = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith('.mjs'))
    .map((entry) => entry.name)
    .sort();

  const missingEntryBundles = expectedEntryBundleNames.filter(
    (bundleName) => !bundleNames.includes(bundleName)
  );
  if (missingEntryBundles.length > 0) {
    throw new Error(
      `Workspace-server build is missing entry bundles: ${missingEntryBundles.join(', ')}`
    );
  }

  const bundleNameSet = new Set(bundleNames);
  const errors: string[] = [];
  for (const bundleName of bundleNames) {
    const source = await readFile(join(distDirectory, bundleName), 'utf8');
    if (/['"][^'"\n]*\.node['"]/.test(source)) {
      errors.push(`${bundleName} contains a native .node binding reference`);
    }
    if (/\b(?:require|__require)\s*\(\s*(?!['"`])/.test(source)) {
      errors.push(`${bundleName} contains a dynamic require call`);
    }
    for (const specifier of collectModuleSpecifiers(source)) {
      if (specifier.startsWith('.')) {
        const importedBundlePath = resolve(distDirectory, dirname(bundleName), specifier);
        const importedBundleName = relative(distDirectory, importedBundlePath);
        if (importedBundleName.startsWith('../') || !bundleNameSet.has(importedBundleName)) {
          errors.push(`${bundleName} imports missing bundle '${specifier}'`);
        }
        continue;
      }
      if (!isAllowedBundleExternal(specifier)) {
        errors.push(`${bundleName} contains unexpected external '${specifier}'`);
      }
    }
  }
  if (errors.length > 0) {
    throw new Error(`Workspace-server bundles are not self-contained:\n${errors.join('\n')}`);
  }

  return bundleNames;
}

function collectModuleSpecifiers(source: string): Set<string> {
  const specifiers = new Set<string>();
  for (const line of source.split('\n')) {
    const importMatch = /^(?:import|export)\s+(?:[^'";]+?\s+from\s+)?['"]([^'"]+)['"];?$/.exec(
      line
    );
    if (importMatch?.[1] !== undefined) {
      specifiers.add(importMatch[1]);
      continue;
    }
    if (line.length > 0) break;
  }

  for (const line of source.split('\n')) {
    const trimmed = line.trimStart();
    if (trimmed.startsWith('*') || trimmed.startsWith('//')) continue;
    for (const match of line.matchAll(/\b(?:require|__require)\s*\(\s*['"]([^'"]+)['"]\s*\)/g)) {
      if (match[1] !== undefined) specifiers.add(match[1]);
    }
  }
  return specifiers;
}

function isAllowedBundleExternal(specifier: string): boolean {
  if (specifier.startsWith('node:') || builtinModules.includes(specifier)) return true;
  return nativePackages.some(
    (packageName) => specifier === packageName || specifier.startsWith(`${packageName}/`)
  );
}

async function extractNodeDistribution(
  nodeVersion: string,
  target: PackageTarget,
  temporaryDirectory: string
): Promise<string> {
  const archivePath = await ensureNodeDistributionArchive(nodeVersion, target);
  const extractionDirectory = join(temporaryDirectory, 'node-distribution');
  await mkdir(extractionDirectory, { recursive: true });
  await runCommand('tar', ['-xJf', archivePath, '-C', extractionDirectory]);

  const distributionDirectory = join(
    extractionDirectory,
    nodeDistributionArchiveName(nodeVersion, target).replace(/\.tar\.xz$/, '')
  );
  if (!(await pathExists(join(distributionDirectory, 'bin/node')))) {
    throw new Error(`Node distribution did not contain bin/node: ${archivePath}`);
  }
  return distributionDirectory;
}

async function ensureNodeDistributionArchive(
  nodeVersion: string,
  target: PackageTarget
): Promise<string> {
  const archiveName = nodeDistributionArchiveName(nodeVersion, target);
  const cacheDirectory = join(packageCacheRoot(), `node-v${nodeVersion}`);
  const archivePath = join(cacheDirectory, archiveName);
  const checksumsUrl = `https://nodejs.org/dist/v${nodeVersion}/SHASUMS256.txt`;
  const checksums = await downloadText(checksumsUrl);
  const expectedChecksum = findChecksum(checksums, archiveName);

  await mkdir(cacheDirectory, { recursive: true });
  if ((await pathExists(archivePath)) && (await sha256File(archivePath)) === expectedChecksum) {
    process.stdout.write(`Using cached ${archiveName}\n`);
    return archivePath;
  }

  const temporaryArchivePath = `${archivePath}.${process.pid}.${randomUUID()}.tmp`;
  try {
    process.stdout.write(`Downloading ${nodeDistributionUrl(nodeVersion, target)}\n`);
    const response = await fetch(nodeDistributionUrl(nodeVersion, target));
    if (!response.ok) {
      throw new Error(`Node download failed with HTTP ${response.status} ${response.statusText}`);
    }
    await writeFile(temporaryArchivePath, Buffer.from(await response.arrayBuffer()));
    const actualChecksum = await sha256File(temporaryArchivePath);
    if (actualChecksum !== expectedChecksum) {
      throw new Error(
        `Checksum mismatch for ${archiveName}: expected ${expectedChecksum}, received ${actualChecksum}`
      );
    }
    await rename(temporaryArchivePath, archivePath);
  } finally {
    await rm(temporaryArchivePath, { force: true });
  }

  return archivePath;
}

async function extractRipgrepDistribution(
  target: PackageTarget,
  temporaryDirectory: string
): Promise<string> {
  const archivePath = await ensureRipgrepArchive(target);
  const extractionDirectory = join(temporaryDirectory, 'ripgrep-distribution');
  await mkdir(extractionDirectory, { recursive: true });
  await runCommand('tar', ['-xzf', archivePath, '-C', extractionDirectory]);

  const distributionDirectory = join(extractionDirectory, ripgrepDistributionName(target));
  for (const requiredPath of ['rg', 'COPYING', 'LICENSE-MIT', 'UNLICENSE']) {
    if (!(await pathExists(join(distributionDirectory, requiredPath)))) {
      throw new Error(`ripgrep distribution did not contain ${requiredPath}: ${archivePath}`);
    }
  }
  return distributionDirectory;
}

async function ensureRipgrepArchive(target: PackageTarget): Promise<string> {
  const archiveName = ripgrepArchiveName(target);
  const cacheDirectory = join(packageCacheRoot(), `ripgrep-v${RIPGREP_VERSION}`);
  const archivePath = join(cacheDirectory, archiveName);
  const expectedChecksum = ripgrepArchiveChecksum(target);

  await mkdir(cacheDirectory, { recursive: true });
  if ((await pathExists(archivePath)) && (await sha256File(archivePath)) === expectedChecksum) {
    process.stdout.write(`Using cached ${archiveName}\n`);
    return archivePath;
  }

  const temporaryArchivePath = `${archivePath}.${process.pid}.${randomUUID()}.tmp`;
  try {
    process.stdout.write(`Downloading ${ripgrepDistributionUrl(target)}\n`);
    const response = await fetch(ripgrepDistributionUrl(target));
    if (!response.ok) {
      throw new Error(
        `ripgrep download failed with HTTP ${response.status} ${response.statusText}`
      );
    }
    await writeFile(temporaryArchivePath, Buffer.from(await response.arrayBuffer()));
    const actualChecksum = await sha256File(temporaryArchivePath);
    if (actualChecksum !== expectedChecksum) {
      throw new Error(
        `Checksum mismatch for ${archiveName}: expected ${expectedChecksum}, ` +
          `received ${actualChecksum}`
      );
    }
    await rename(temporaryArchivePath, archivePath);
  } finally {
    await rm(temporaryArchivePath, { force: true });
  }

  return archivePath;
}

async function downloadText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Download failed for ${url}: HTTP ${response.status} ${response.statusText}`);
  }
  return response.text();
}

function findChecksum(checksums: string, archiveName: string): string {
  for (const line of checksums.split('\n')) {
    const [checksum, listedName] = line.trim().split(/\s+/, 2);
    if (listedName?.replace(/^\*/, '') === archiveName && /^[a-f\d]{64}$/.test(checksum ?? '')) {
      return checksum as string;
    }
  }
  throw new Error(`SHASUMS256.txt did not contain ${archiveName}`);
}

function packageCacheRoot(): string {
  return (
    process.env['EMDASH_WS_PACKAGE_CACHE_DIR'] ??
    join(homedir(), '.cache', 'emdash', 'workspace-server')
  );
}

async function sha256File(path: string): Promise<string> {
  const hash = createHash('sha256');
  hash.update(await readFile(path));
  return hash.digest('hex');
}

async function installDarwinRuntimeDependencies(
  nodeDistributionDirectory: string,
  temporaryDirectory: string
): Promise<string> {
  const stagingDirectory = join(temporaryDirectory, 'darwin-runtime-deps');
  const nodeBinDirectory = join(nodeDistributionDirectory, 'bin');
  const nodePath = join(nodeBinDirectory, 'node');
  const npmPath = join(nodeDistributionDirectory, 'lib/node_modules/npm/bin/npm-cli.js');
  const existingPath = process.env['PATH'];

  await mkdir(stagingDirectory, { recursive: true });
  await copyFile(
    join(runtimeDepsDirectory, 'package.json'),
    join(stagingDirectory, 'package.json')
  );
  await runCommand(
    nodePath,
    [npmPath, 'install', '--omit=dev', '--no-audit', '--no-fund', '--package-lock=false'],
    {
      cwd: stagingDirectory,
      env: {
        ...process.env,
        PATH: existingPath === undefined ? nodeBinDirectory : `${nodeBinDirectory}:${existingPath}`,
        npm_config_update_notifier: 'false',
      },
    }
  );
  return join(stagingDirectory, 'node_modules');
}

async function buildLinuxRuntimeDependencies(
  nodeVersion: string,
  target: PackageTarget,
  temporaryDirectory: string
): Promise<string> {
  if (target.dockerPlatform === undefined) {
    throw new Error(`Target ${target.id} does not define a Docker platform`);
  }

  const outputDirectory = join(temporaryDirectory, 'linux-runtime-deps');
  await mkdir(outputDirectory, { recursive: true });
  await runCommand('docker', [
    'buildx',
    'build',
    '--platform',
    target.dockerPlatform,
    '--progress',
    'plain',
    '--file',
    dockerfilePath,
    '--build-arg',
    `NODE_VERSION=${nodeVersion}`,
    '--output',
    `type=local,dest=${outputDirectory}`,
    runtimeDepsDirectory,
  ]);

  const nodeModules = join(outputDirectory, 'node_modules');
  if (!(await pathExists(nodeModules))) {
    throw new Error(`Docker build did not export node_modules for ${target.id}`);
  }
  return nodeModules;
}

async function assembleArtifact(options: {
  target: PackageTarget;
  packageMetadata: PackageMetadata;
  protocolVersion: string;
  nodeVersion: string;
  nodeDistributionDirectory: string;
  runtimeNodeModules: string;
  ripgrepDistributionDirectory: string;
  bundleNames: string[];
  adapterAssets: readonly PackageAdapterAssetInfo[];
  temporaryDirectory: string;
}): Promise<string> {
  const {
    target,
    packageMetadata,
    protocolVersion,
    nodeVersion,
    nodeDistributionDirectory,
    runtimeNodeModules,
    ripgrepDistributionDirectory,
    bundleNames,
    adapterAssets,
    temporaryDirectory,
  } = options;
  const artifactDirectory = join(temporaryDirectory, 'artifact', artifactRootName);
  const binDirectory = join(artifactDirectory, 'bin');
  const distDirectory = join(artifactDirectory, 'dist');
  const ripgrepLicenseDirectory = join(artifactDirectory, 'licenses', 'ripgrep');
  const launcherPath = join(binDirectory, 'emdash-workspace-server');
  const nodePath = join(artifactDirectory, 'node');
  const ripgrepPath = join(binDirectory, 'rg');

  await mkdir(binDirectory, { recursive: true });
  await mkdir(distDirectory, { recursive: true });
  await mkdir(ripgrepLicenseDirectory, { recursive: true });
  await copyFile(join(nodeDistributionDirectory, 'bin/node'), nodePath);
  await chmod(nodePath, 0o755);
  await copyFile(join(ripgrepDistributionDirectory, 'rg'), ripgrepPath);
  await chmod(ripgrepPath, 0o755);
  for (const licenseFile of ['COPYING', 'LICENSE-MIT', 'UNLICENSE']) {
    await copyFile(
      join(ripgrepDistributionDirectory, licenseFile),
      join(ripgrepLicenseDirectory, licenseFile)
    );
  }
  await cp(runtimeNodeModules, join(artifactDirectory, 'node_modules'), { recursive: true });

  for (const bundleName of bundleNames) {
    await copyFile(join(appDirectory, 'dist', bundleName), join(distDirectory, bundleName));
  }
  await cp(
    join(repositoryDirectory, 'packages/plugins/dist/adapters'),
    join(distDirectory, 'adapters'),
    {
      recursive: true,
    }
  );
  await validateBuiltAdapterDirectory(join(distDirectory, 'adapters'), adapterAssets);

  await writeFile(launcherPath, createLauncher(packageMetadata.version));
  await chmod(launcherPath, 0o755);
  await writeFile(
    join(artifactDirectory, 'manifest.json'),
    `${JSON.stringify(
      createArtifactManifest({
        name: packageMetadata.name,
        version: packageMetadata.version,
        protocolVersion,
        nodeVersion,
        target,
      }),
      undefined,
      2
    )}\n`
  );

  return artifactDirectory;
}

async function verifyArtifact(archivePath: string, target: PackageTarget): Promise<void> {
  const extractionDirectory = await mkdtemp(join(tmpdir(), `emdash-ws-verify-${target.id}-`));
  try {
    await runCommand('tar', ['-xzf', archivePath, '-C', extractionDirectory]);
    const extractedArtifact = join(extractionDirectory, artifactRootName);
    if (target.os === 'linux') {
      await verifyLinuxArtifact(extractedArtifact, target);
    } else {
      await verifyLocalArtifact(extractedArtifact);
    }
  } finally {
    await rm(extractionDirectory, { recursive: true, force: true });
  }
}

async function verifyLocalArtifact(extractedArtifact: string): Promise<void> {
  const runtimeDirectory = await mkdtemp('/tmp/emdash-ws-smoke-');
  const launcherPath = join(extractedArtifact, 'bin/emdash-workspace-server');
  const ripgrepPath = join(extractedArtifact, 'bin/rg');
  const socketPath = join(runtimeDirectory, 'run/workspace.sock');
  const searchDirectory = join(runtimeDirectory, 'search');
  const lifecycleArgs = ['--socket-path', socketPath];

  try {
    await mkdir(searchDirectory, { recursive: true });
    await writeFile(join(searchDirectory, 'needle.txt'), 'bundled-ripgrep-smoke\n', 'utf8');
    await runCommand(ripgrepPath, ['--version']);
    await runCommand(ripgrepPath, [
      '--fixed-strings',
      '--quiet',
      'bundled-ripgrep-smoke',
      searchDirectory,
    ]);
    await runCommand(launcherPath, ['start', ...lifecycleArgs]);
    await runCommand(launcherPath, ['status', ...lifecycleArgs]);
    await runCommand(launcherPath, ['stop', ...lifecycleArgs]);
  } finally {
    await runCommand(launcherPath, ['stop', ...lifecycleArgs], { stdio: 'ignore' }).catch(
      () => undefined
    );
    await rm(runtimeDirectory, { recursive: true, force: true });
  }
}

async function verifyLinuxArtifact(
  extractedArtifact: string,
  target: PackageTarget
): Promise<void> {
  if (target.dockerPlatform === undefined) {
    throw new Error(`Target ${target.id} does not define a Docker platform`);
  }

  const smokeScript = `set -eu
server=/opt/emdash-workspace-server/bin/emdash-workspace-server
rg=/opt/emdash-workspace-server/bin/rg
socket=/tmp/emdash-smoke/run/workspace.sock
mkdir -p /tmp/emdash-smoke/run
mkdir -p /tmp/emdash-smoke/search
printf '%s\\n' bundled-ripgrep-smoke > /tmp/emdash-smoke/search/needle.txt
cleanup() { "$server" stop --socket-path "$socket" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
"$rg" --version
"$rg" --fixed-strings --quiet bundled-ripgrep-smoke /tmp/emdash-smoke/search
"$server" start --socket-path "$socket"
"$server" status --socket-path "$socket"
"$server" stop --socket-path "$socket"
`;

  await runCommand('docker', [
    'run',
    '--rm',
    '--platform',
    target.dockerPlatform,
    '--volume',
    `${extractedArtifact}:/opt/emdash-workspace-server:ro`,
    '--entrypoint',
    '/bin/sh',
    'debian:bookworm-slim',
    '-c',
    smokeScript,
  ]);
}

async function runCommand(
  command: string,
  args: string[],
  options: {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    stdio?: StdioOptions;
  } = {}
): Promise<void> {
  await new Promise<void>((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: options.stdio ?? 'inherit',
    });
    child.once('error', rejectPromise);
    child.once('exit', (code, signal) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      rejectPromise(
        new Error(
          `${command} exited ${signal === null ? `with code ${String(code)}` : `on signal ${signal}`}`
        )
      );
    });
  });
}

async function runCommandOutput(
  command: string,
  args: string[],
  options: {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
  } = {}
): Promise<string> {
  return await new Promise<string>((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on('data', (chunk: string) => {
      stderr += chunk;
    });
    child.once('error', rejectPromise);
    child.once('exit', (code, signal) => {
      if (code === 0) {
        resolvePromise(stdout);
        return;
      }
      const output = stderr.trim();
      rejectPromise(
        new Error(
          `${command} exited ${signal === null ? `with code ${String(code)}` : `on signal ${signal}`}${
            output ? `: ${output}` : ''
          }`
        )
      );
    });
  });
}

async function pathExists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (isNodeError(error) && error.code === 'ENOENT') return false;
    throw error;
  }
}

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && 'code' in error;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function printUsage(): void {
  process.stdout
    .write(`Usage: pnpm run package --target <target> [--target <target> ...] [--version <version>] [--verify]

Targets:
  linux-x64
  linux-arm64
  darwin-arm64
`);
}

void main().catch((error: unknown) => {
  process.stderr.write(
    `workspace-server packaging failed: ${error instanceof Error ? error.message : String(error)}\n`
  );
  process.exit(1);
});
