import { hostRef } from '@emdash/core/primitives/host/api';
import {
  runtimeHostIdentityLost,
  runtimeHostNotConfigured,
  runtimeHostUnavailable,
  type RuntimeUnavailableReason,
} from '@emdash/core/primitives/runtime-resolution/api';
import { describe, expect, it } from 'vitest';
import type { ProjectAttachmentError, ProjectAttachmentState } from '@core/features/projects/api';
import { deriveProjectHostAccessState } from '@core/features/projects/api/browser/stores/project-context';
import type { HostAvailabilityState } from '@core/services/hosts/api';

const host = hostRef('remote', 'ssh-private-id');
const oldRepositoryFailure = {
  type: 'repository-unavailable',
  path: '/private/repository',
  message: 'raw filesystem failure',
} as const;

describe('deriveProjectHostAccessState', () => {
  it.each<
    [
      label: string,
      availability: HostAvailabilityState | undefined,
      attachment: ProjectAttachmentState | undefined,
      expected: ReturnType<typeof deriveProjectHostAccessState>,
    ]
  >([
    [
      'availability still loading',
      undefined,
      undefined,
      {
        kind: 'degraded',
        situation: 'offline',
        recovery: 'automatic',
      },
    ],
    [
      'suspended Host supersedes an older Project failure',
      { kind: 'suspended', reason: 'user-disconnected' },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'suspended',
        recovery: 'manual',
      },
    ],
    [
      'connecting Host supersedes an older Project failure',
      { kind: 'preparing', phase: 'connecting', attempt: 1 },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'connecting',
        recovery: 'automatic',
      },
    ],
    [
      'provisioning Host supersedes an older Project failure',
      { kind: 'preparing', phase: 'provisioning', attempt: 1 },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'provisioning',
        recovery: 'automatic',
      },
    ],
    [
      'handshaking Host supersedes an older Project failure',
      { kind: 'preparing', phase: 'handshaking', attempt: 1 },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'handshaking',
        recovery: 'automatic',
      },
    ],
    [
      'eligible unavailable Host is offline between active runs',
      { kind: 'unavailable', recovery: 'eligible' },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'offline',
        recovery: 'automatic',
      },
    ],
    [
      'waiting unavailable Host is recovering',
      {
        kind: 'unavailable',
        issue: runtimeHostUnavailable(host, 'connection-failed', 'raw connection failure'),
        recovery: 'waiting',
        nextAttemptAt: 12_000,
      },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'recovering',
        recovery: 'automatic',
        issue: runtimeHostUnavailable(host, 'connection-failed', 'raw connection failure'),
        nextAttemptAt: 12_000,
      },
    ],
    [
      'manual unavailable Host needs attention',
      {
        kind: 'unavailable',
        issue: runtimeHostUnavailable(host, 'install-failed', 'raw install failure'),
        recovery: 'manual',
      },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'attention',
        recovery: 'manual',
        issue: runtimeHostUnavailable(host, 'install-failed', 'raw install failure'),
      },
    ],
    [
      'blocked unavailable Host needs correction',
      {
        kind: 'unavailable',
        issue: runtimeHostUnavailable(host, 'unsupported-platform', 'raw platform failure'),
        recovery: 'blocked',
      },
      { kind: 'absent', lastFailure: oldRepositoryFailure },
      {
        kind: 'degraded',
        situation: 'attention',
        recovery: 'blocked',
        issue: runtimeHostUnavailable(host, 'unsupported-platform', 'raw platform failure'),
      },
    ],
    [
      'retained attachment from an earlier Host generation',
      { kind: 'ready', generation: 3 },
      { kind: 'attached', establishedHostGeneration: 2 },
      { kind: 'ready', hostGeneration: 3 },
    ],
    [
      'attached Project in the current Host generation',
      { kind: 'ready', generation: 3 },
      { kind: 'attached', establishedHostGeneration: 3 },
      { kind: 'ready', hostGeneration: 3 },
    ],
    [
      'ready Host before attachment publication',
      { kind: 'ready', generation: 2 },
      undefined,
      {
        kind: 'degraded',
        situation: 'attaching',
        recovery: 'automatic',
      },
    ],
    [
      'ready Host with absent attachment',
      { kind: 'ready', generation: 2 },
      { kind: 'absent' },
      {
        kind: 'degraded',
        situation: 'attaching',
        recovery: 'automatic',
      },
    ],
    [
      'ready Host with attachment in progress',
      { kind: 'ready', generation: 2 },
      { kind: 'attaching', hostGeneration: 2, attemptId: 'attempt-1' },
      {
        kind: 'degraded',
        situation: 'attaching',
        recovery: 'automatic',
      },
    ],
  ])('derives $label with the fixed precedence', (_label, availability, attachment, expected) => {
    expect(deriveProjectHostAccessState(availability, attachment)).toEqual(expected);
  });

  const ready = { kind: 'ready', generation: 7 } as const;
  const runtimeCases: Array<
    [
      reason: RuntimeUnavailableReason,
      recovery: Extract<
        NonNullable<ReturnType<typeof deriveProjectHostAccessState>>,
        { kind: 'degraded' }
      >['recovery'],
    ]
  > = [
    ['offline', 'automatic'],
    ['connection-failed', 'automatic'],
    ['daemon-start-failed', 'automatic'],
    ['artifact-download-failed', 'manual'],
    ['install-failed', 'manual'],
    ['unsupported-platform', 'blocked'],
    ['protocol-upgrade-client', 'blocked'],
    ['protocol-upgrade-server', 'blocked'],
    ['runtime-unavailable', 'automatic'],
  ];

  it.each<[label: string, issue: ProjectAttachmentError, recovery: string]>([
    ...runtimeCases.map(
      ([reason, recovery]) =>
        [reason, runtimeHostUnavailable(host, reason, `raw:${reason}`), recovery] satisfies [
          string,
          ProjectAttachmentError,
          string,
        ]
    ),
    ['not-configured', runtimeHostNotConfigured(host, 'raw not-configured failure'), 'blocked'],
    ['host-identity-lost', runtimeHostIdentityLost(host, 'raw identity failure'), 'blocked'],
    ['repository-missing', { type: 'repository-missing', path: '/raw/path' }, 'manual'],
    [
      'repository-unavailable',
      {
        type: 'repository-unavailable',
        path: '/raw/path',
        message: 'raw filesystem failure',
      },
      'manual',
    ],
    [
      'unexpected',
      { type: 'unexpected', stage: 'session-open', message: 'raw provider failure' },
      'manual',
    ],
  ])('classifies $label as $recovery attention', (_label, issue, recovery) => {
    expect(
      deriveProjectHostAccessState(ready, {
        kind: 'absent',
        lastFailure: issue,
        attemptedHostGeneration: 7,
      })
    ).toEqual({
      kind: 'degraded',
      situation: 'attention',
      recovery,
      issue,
    });
  });

  it('keeps attachment waiting automatic inside the ready Host generation', () => {
    const issue = {
      type: 'attachment-unavailable',
      host,
      phase: 'waiting',
    } as const;

    expect(
      deriveProjectHostAccessState(ready, {
        kind: 'absent',
        lastFailure: issue,
        attemptedHostGeneration: 7,
      })
    ).toEqual({
      kind: 'degraded',
      situation: 'attaching',
      recovery: 'automatic',
      issue,
    });
  });

  it('returns no stable access state when the durable Project is missing', () => {
    expect(
      deriveProjectHostAccessState(ready, {
        kind: 'absent',
        lastFailure: { type: 'project-missing', projectId: 'project-private-id' },
        attemptedHostGeneration: 7,
      })
    ).toBeNull();
  });
});
