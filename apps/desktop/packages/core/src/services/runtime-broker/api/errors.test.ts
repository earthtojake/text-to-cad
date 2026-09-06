import { describe, expect, it } from 'vitest';
import { hostRef } from '../../../primitives/host/api';
import {
  isRuntimeResolveError,
  runtimeHostIdentityLost,
  runtimeHostNotConfigured,
  runtimeHostUnavailable,
  runtimeResolveErrorAsError,
  runtimeResolveErrorSchema,
  type RuntimeUnavailableReason,
} from './errors';

describe('RuntimeResolveError helpers', () => {
  it('constructs and recognizes both resolver error variants', () => {
    const remote = hostRef('remote', 'ssh-1');
    const unavailable = runtimeHostUnavailable(remote, 'Remote runtime unavailable');
    const notConfigured = runtimeHostNotConfigured(remote, 'Remote runtime not configured');

    expect(isRuntimeResolveError(unavailable)).toBe(true);
    expect(isRuntimeResolveError(notConfigured)).toBe(true);
  });

  it('preserves the discriminant when an exception boundary is unavoidable', () => {
    const payload = runtimeHostUnavailable(
      hostRef('remote', 'ssh-1'),
      'Remote runtime unavailable'
    );

    expect(runtimeResolveErrorAsError(payload)).toMatchObject(payload);
  });

  it('round-trips every semantic runtime-resolution reason through its public schema', () => {
    const host = hostRef('remote', 'ssh-1');
    const reasons: RuntimeUnavailableReason[] = [
      'offline',
      'connection-failed',
      'daemon-start-failed',
      'artifact-download-failed',
      'install-failed',
      'unsupported-platform',
      'protocol-upgrade-client',
      'protocol-upgrade-server',
      'runtime-unavailable',
    ];
    const errors = [
      ...reasons.map((reason) => runtimeHostUnavailable(host, reason, `semantic:${reason}`)),
      runtimeHostNotConfigured(host, 'not configured'),
      runtimeHostIdentityLost(host, 'identity lost'),
    ];

    for (const error of errors) {
      expect(runtimeResolveErrorSchema.parse(JSON.parse(JSON.stringify(error)))).toEqual(error);
    }
  });

  it('normalizes legacy Wire payloads without making the type guard unsound', () => {
    const legacy = {
      type: 'host-unavailable',
      host: hostRef('remote', 'ssh-1'),
      message: 'legacy unavailable',
    };

    expect(runtimeResolveErrorSchema.parse(legacy)).toEqual({
      ...legacy,
      reason: 'runtime-unavailable',
    });
    expect(isRuntimeResolveError(legacy)).toBe(false);
  });
});
