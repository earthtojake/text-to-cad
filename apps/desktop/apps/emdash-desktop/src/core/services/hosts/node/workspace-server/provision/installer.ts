import path from 'node:path';
import { quoteArg } from '@emdash/core/primitives/exec/api';
import {
  channelPointerPath,
  parseChannelPointer,
  protocolMajor,
  type ReleaseChannel,
} from '@emdash/core/workspace-server';
import type { SshClientProxy } from '@core/primitives/ssh/api/node/ssh-client-proxy';
import { validateWorkspaceServerVersion, type WorkspaceServerLayout } from '../layout';
import type { WorkspaceServerSshPort } from '../ports';

export const DEFAULT_WORKSPACE_SERVER_INSTALL_BASE_URL =
  'https://github.com/amywork777/hardcore/releases/download/workspace-server';

export type WorkspaceServerInstallErrorCode =
  | 'unsupported-platform'
  | 'artifact-download-failed'
  | 'install-failed';

export class WorkspaceServerInstallError extends Error {
  readonly name = 'WorkspaceServerInstallError';

  constructor(
    readonly code: WorkspaceServerInstallErrorCode,
    message: string,
    options?: ErrorOptions
  ) {
    super(message, options);
  }
}

export type WorkspaceServerInstallerOptions = {
  ssh: WorkspaceServerSshPort;
  baseUrl?: string;
  releaseChannel?: ReleaseChannel;
};

export type WorkspaceServerInstallOptions = {
  connectionId: string;
  layout: WorkspaceServerLayout;
  signal?: AbortSignal;
  version?: string;
};

export class WorkspaceServerInstaller {
  private readonly ssh: WorkspaceServerSshPort;
  private readonly baseUrl: string;
  private readonly releaseChannel: ReleaseChannel;

  constructor(options: WorkspaceServerInstallerOptions) {
    this.ssh = options.ssh;
    this.baseUrl = options.baseUrl ?? DEFAULT_WORKSPACE_SERVER_INSTALL_BASE_URL;
    this.releaseChannel = options.releaseChannel ?? 'stable';
  }

  async installedVersion(
    connectionId: string,
    layout: WorkspaceServerLayout,
    signal?: AbortSignal
  ): Promise<string | undefined> {
    const proxy = await this.ssh.ensureProxy(connectionId);
    return await this.installedVersionFromProxy(proxy, layout, signal);
  }

  async install(options: WorkspaceServerInstallOptions): Promise<void> {
    const selectedVersion =
      options.version ?? (await this.availableVersion(options.connectionId, options.signal));
    const command = buildWorkspaceServerInstallCommand(this.baseUrl, selectedVersion);
    const proxy = await this.ssh.ensureProxy(options.connectionId);
    const result = await proxy.execScript(command, {
      signal: options.signal,
      timeoutMs: 5 * 60_000,
      maxStdoutBytes: 256 * 1_024,
      maxStderrBytes: 256 * 1_024,
    });
    if (result.exitCode !== 0) {
      const code =
        result.exitCode === 40
          ? 'unsupported-platform'
          : result.exitCode === 41
            ? 'artifact-download-failed'
            : 'install-failed';
      throw new WorkspaceServerInstallError(
        code,
        `Workspace-server installation failed: ${result.stderr.trim() || `exit ${result.exitCode}`}`
      );
    }

    const installedVersion = await this.installedVersionFromProxy(
      proxy,
      options.layout,
      options.signal
    );
    if (installedVersion !== selectedVersion) {
      throw new WorkspaceServerInstallError(
        'install-failed',
        installedVersion === undefined
          ? `Workspace-server installation did not select requested version ${selectedVersion}`
          : `Workspace-server installation installed ${installedVersion} instead of ${selectedVersion}`
      );
    }
  }

  private async installedVersionFromProxy(
    proxy: SshClientProxy,
    layout: WorkspaceServerLayout,
    signal?: AbortSignal
  ): Promise<string | undefined> {
    const result = await proxy.exec(
      { command: 'readlink', args: ['--', layout.currentLink] },
      {
        signal,
        timeoutMs: 10_000,
        maxStdoutBytes: 4_096,
        maxStderrBytes: 4_096,
      }
    );
    if (result.exitCode !== 0) return undefined;

    const linkTarget = result.stdout.trim();
    const version = path.posix.basename(linkTarget);
    try {
      validateWorkspaceServerVersion(version);
    } catch (error) {
      throw new WorkspaceServerInstallError(
        'install-failed',
        `The managed workspace-server current link is invalid: ${result.stdout.trim()}`,
        { cause: error }
      );
    }
    if (linkTarget !== `versions/${version}` && linkTarget !== layout.versionDirectory(version)) {
      throw new WorkspaceServerInstallError(
        'install-failed',
        `The managed workspace-server current link points outside versions/: ${linkTarget}`
      );
    }
    return version;
  }

  async availableVersion(connectionId: string, signal?: AbortSignal): Promise<string> {
    const expectedProtocolMajor = protocolMajor();
    const proxy = await this.ssh.ensureProxy(connectionId);
    const result = await proxy.execScript(
      buildWorkspaceServerChannelPointerCommand(
        this.baseUrl,
        this.releaseChannel,
        expectedProtocolMajor
      ),
      {
        signal,
        timeoutMs: 10_000,
        maxStdoutBytes: 4_096,
        maxStderrBytes: 4_096,
      }
    );
    if (result.exitCode !== 0) {
      throw new WorkspaceServerInstallError(
        'artifact-download-failed',
        `Could not resolve the workspace-server ${this.releaseChannel} channel pointer: ${
          result.stderr.trim() || `exit ${result.exitCode}`
        }`
      );
    }

    const pointer = parseChannelPointer(result.stdout, expectedProtocolMajor);
    if (!pointer.success) {
      const reason =
        pointer.error.type === 'invalid'
          ? pointer.error.reason
          : `expected protocol major ${pointer.error.expected}, received ${pointer.error.actual}`;
      throw new WorkspaceServerInstallError(
        'artifact-download-failed',
        `The workspace-server ${this.releaseChannel} channel pointer is invalid: ${reason}`
      );
    }
    return pointer.data.artifactVersion;
  }
}

export function buildWorkspaceServerChannelPointerCommand(
  baseUrl: string,
  channel: ReleaseChannel,
  expectedProtocolMajor: number
): string {
  const normalizedBaseUrl = validateInstallBaseUrl(baseUrl);
  const pointerUrl = new URL(
    channelPointerPath(channel, expectedProtocolMajor),
    ensureTrailingSlash(normalizedBaseUrl)
  );
  const quotedPointerUrl = quoteArg(pointerUrl.href, 'posix');
  const stableFallbackUrl =
    channel === 'canary'
      ? quoteArg(
          new URL(
            channelPointerPath('stable', expectedProtocolMajor),
            ensureTrailingSlash(normalizedBaseUrl)
          ).href,
          'posix'
        )
      : undefined;
  const curlCommand = stableFallbackUrl
    ? `curl -fsSL -- ${quotedPointerUrl} 2>/dev/null || curl -fsSL -- ${stableFallbackUrl}`
    : `curl -fsSL -- ${quotedPointerUrl}`;
  const wgetCommand = stableFallbackUrl
    ? `wget -qO- -- ${quotedPointerUrl} 2>/dev/null || wget -qO- -- ${stableFallbackUrl}`
    : `wget -qO- -- ${quotedPointerUrl}`;
  return `set -eu
if command -v curl >/dev/null 2>&1; then
  ${curlCommand}
elif command -v wget >/dev/null 2>&1; then
  ${wgetCommand}
else
  echo "curl or wget is required to download workspace-server metadata" >&2
  exit 41
fi`;
}

export function buildWorkspaceServerInstallCommand(baseUrl: string, version: string): string {
  const normalizedBaseUrl = validateInstallBaseUrl(baseUrl);
  const selectedVersion = validateWorkspaceServerVersion(version);
  const scriptUrl = new URL(`${selectedVersion}/install.sh`, ensureTrailingSlash(normalizedBaseUrl))
    .href;
  const quotedScriptUrl = quoteArg(scriptUrl, 'posix');
  const quotedBaseUrl = quoteArg(normalizedBaseUrl, 'posix');
  const quotedVersion = quoteArg(selectedVersion, 'posix');
  return `set -eu
install_script=\${TMPDIR:-/tmp}/emdash-workspace-server-install-$$.sh
cleanup() { rm -f -- "$install_script"; }
trap cleanup EXIT HUP INT TERM
if ! curl -fsSL --output "$install_script" -- ${quotedScriptUrl}; then
  exit 41
fi
sh "$install_script" --base-url ${quotedBaseUrl} --version ${quotedVersion}`;
}

function validateInstallBaseUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch (error) {
    throw new WorkspaceServerInstallError(
      'artifact-download-failed',
      'Workspace-server install base URL is invalid',
      { cause: error }
    );
  }
  if (!['https:', 'http:'].includes(url.protocol)) {
    throw new WorkspaceServerInstallError(
      'artifact-download-failed',
      `Unsupported workspace-server install URL protocol '${url.protocol}'`
    );
  }
  return url.href.replace(/\/$/, '');
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith('/') ? value : `${value}/`;
}
