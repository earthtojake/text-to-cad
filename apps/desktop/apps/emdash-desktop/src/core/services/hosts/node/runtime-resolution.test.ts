import { hostRef } from '@emdash/core/primitives/host/api';
import {
  runtimeHostIdentityLost,
  runtimeHostNotConfigured,
  runtimeHostUnavailable,
  type RuntimeResolveError,
} from '@emdash/core/primitives/runtime-resolution/api';
import { describe, expect, it } from 'vitest';
import { SshConnectionNotFoundError } from '@core/primitives/ssh/api';
import { translateHostPreparationError } from './runtime-resolution';
import { WorkspaceServerProtocolError, WorkspaceServerProvisionError } from './workspace-server';

const host = hostRef('remote', 'ssh-private-id');

describe('translateHostPreparationError', () => {
  it.each<
    [
      label: string,
      phase: Parameters<typeof translateHostPreparationError>[1],
      error: unknown,
      expected: RuntimeResolveError,
    ]
  >([
    [
      'SSH connection failure',
      'connecting',
      new WorkspaceServerProvisionError('connection-failed', 'raw connection failure'),
      runtimeHostUnavailable(host, 'connection-failed', 'Host connection failed'),
    ],
    [
      'daemon start failure',
      'provisioning',
      new WorkspaceServerProvisionError('daemon-start-failed', 'raw daemon failure'),
      runtimeHostUnavailable(host, 'daemon-start-failed', 'Host runtime could not start'),
    ],
    [
      'artifact download failure',
      'provisioning',
      new WorkspaceServerProvisionError('artifact-download-failed', 'raw download failure'),
      runtimeHostUnavailable(host, 'artifact-download-failed', 'Host runtime download failed'),
    ],
    [
      'install failure',
      'provisioning',
      new WorkspaceServerProvisionError('install-failed', 'raw install failure'),
      runtimeHostUnavailable(host, 'install-failed', 'Host runtime installation failed'),
    ],
    [
      'unsupported platform',
      'provisioning',
      new WorkspaceServerProvisionError('unsupported-platform', 'raw platform failure'),
      runtimeHostUnavailable(host, 'unsupported-platform', 'Host platform is not supported'),
    ],
    [
      'client protocol upgrade',
      'handshaking',
      new WorkspaceServerProtocolError({
        type: 'protocol-incompatible',
        action: 'upgrade-client',
        clientProtocolVersion: '1.0.0',
        serverProtocolVersion: '2.0.0',
      }),
      runtimeHostUnavailable(
        host,
        'protocol-upgrade-client',
        'The desktop app must be updated for this Host'
      ),
    ],
    [
      'server protocol upgrade',
      'handshaking',
      new WorkspaceServerProvisionError('protocol-incompatible', 'raw protocol failure', {
        cause: new WorkspaceServerProtocolError({
          type: 'protocol-incompatible',
          action: 'upgrade-server',
          clientProtocolVersion: '2.0.0',
          serverProtocolVersion: '1.0.0',
        }),
      }),
      runtimeHostUnavailable(host, 'protocol-upgrade-server', 'The Host runtime must be updated'),
    ],
    [
      'unclassified protocol failure',
      'handshaking',
      new WorkspaceServerProvisionError('protocol-incompatible', 'raw protocol failure'),
      runtimeHostUnavailable(host, 'runtime-unavailable', 'Host runtime is unavailable'),
    ],
    [
      'runtime handshake failure',
      'handshaking',
      new Error('raw handshake failure'),
      runtimeHostUnavailable(host, 'runtime-unavailable', 'Host runtime is unavailable'),
    ],
    [
      'deleted SSH identity wrapped by provisioning',
      'provisioning',
      new WorkspaceServerProvisionError('connection-failed', 'raw provisioning failure', {
        cause: new SshConnectionNotFoundError('ssh-private-id'),
      }),
      runtimeHostIdentityLost(host, 'Host identity is no longer configured'),
    ],
  ])('translates $label to a stable semantic outcome', (_label, phase, error, expected) => {
    expect(translateHostPreparationError(host, phase, error)).toEqual(expected);
  });

  it.each([
    runtimeHostNotConfigured(host, 'stable not-configured outcome'),
    runtimeHostIdentityLost(host, 'stable identity-lost outcome'),
  ])('passes an existing typed outcome through unchanged', (error) => {
    expect(translateHostPreparationError(host, 'connecting', error)).toBe(error);
  });
});
