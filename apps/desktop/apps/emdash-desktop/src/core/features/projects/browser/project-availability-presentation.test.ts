import { hostRef } from '@emdash/core/primitives/host/api';
import {
  runtimeHostIdentityLost,
  runtimeHostNotConfigured,
  runtimeHostUnavailable,
  type RuntimeUnavailableReason,
} from '@emdash/core/primitives/runtime-resolution/api';
import { describe, expect, it } from 'vitest';
import type { ProjectAttachmentError } from '@core/features/projects/api/attachments';
import type { ProjectIssueRecovery } from '@core/features/projects/api/browser/project-attachment-recovery';
import type { ProjectHostAccessState } from '@core/features/projects/api/browser/stores/project-context';
import {
  classifyProjectAttachmentIssue,
  classifyProjectAvailability,
  projectLiveActionDisabledReason,
} from './project-availability-presentation';

const host = hostRef('remote', 'connection-private-id');
const runtimeReasons: RuntimeUnavailableReason[] = [
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
const runtimeIssues = Object.fromEntries(
  runtimeReasons.map((reason) => [
    reason,
    runtimeHostUnavailable(host, reason, `raw lower-level ${reason} message`),
  ])
) as Record<RuntimeUnavailableReason, ProjectAttachmentError>;
const issues = {
  ...runtimeIssues,
  'not-configured': runtimeHostNotConfigured(host, 'raw not-configured message'),
  'host-identity-lost': runtimeHostIdentityLost(host, 'raw identity message'),
  'attachment-unavailable': {
    type: 'attachment-unavailable',
    host,
    phase: 'waiting',
  },
  'repository-missing': {
    type: 'repository-missing',
    path: '/private/repository/path',
  },
  'repository-unavailable': {
    type: 'repository-unavailable',
    path: '/private/repository/path',
    message: 'raw filesystem message',
  },
  unexpected: {
    type: 'unexpected',
    stage: 'session-open',
    message: 'raw provider message',
  },
  'project-missing': {
    type: 'project-missing',
    projectId: 'project-private-id',
  },
} satisfies Record<string, ProjectAttachmentError>;

type ExpectedIssue = [
  semantic: keyof typeof issues,
  recovery: ProjectIssueRecovery,
  actions: string[],
];

const expectedIssues: ExpectedIssue[] = [
  ['offline', 'automatic', ['retry', 'diagnostics']],
  ['connection-failed', 'automatic', ['retry', 'diagnostics']],
  ['daemon-start-failed', 'automatic', ['retry', 'diagnostics']],
  ['artifact-download-failed', 'manual', ['retry', 'diagnostics']],
  ['install-failed', 'manual', ['retry', 'diagnostics']],
  ['unsupported-platform', 'blocked', ['diagnostics']],
  ['protocol-upgrade-client', 'blocked', ['update-client']],
  ['protocol-upgrade-server', 'blocked', ['diagnostics', 'retry']],
  ['runtime-unavailable', 'automatic', ['retry', 'diagnostics']],
  ['not-configured', 'blocked', ['configure']],
  ['host-identity-lost', 'blocked', ['relink-project', 'remove-project']],
  ['attachment-unavailable', 'automatic', []],
  ['repository-missing', 'manual', ['retry']],
  ['repository-unavailable', 'manual', ['retry', 'diagnostics']],
  ['unexpected', 'manual', ['retry', 'diagnostics']],
  ['project-missing', 'dispose-context', []],
];

describe('classifyProjectAttachmentIssue', () => {
  it.each(expectedIssues)(
    'classifies %s with its fixed recovery and corrective actions',
    (semantic, recovery, actions) => {
      expect(classifyProjectAttachmentIssue(issues[semantic]!)).toEqual({
        semantic,
        recovery,
        correctiveActions: actions,
      });
    }
  );
});

describe('classifyProjectAvailability', () => {
  const ssh = { kind: 'ssh', machineName: 'Orion' } as const;
  const local = { kind: 'local' } as const;

  it.each<
    [label: string, state: ProjectHostAccessState, title: string | null, actionLabels: string[]]
  >([
    ['ready', { kind: 'ready', hostGeneration: 4 }, null, []],
    [
      'suspended',
      { kind: 'degraded', situation: 'suspended', recovery: 'manual' },
      'Orion is offline',
      ['Connect'],
    ],
    [
      'offline',
      { kind: 'degraded', situation: 'offline', recovery: 'automatic' },
      'Orion is offline',
      ['Connect'],
    ],
    [
      'connecting',
      { kind: 'degraded', situation: 'connecting', recovery: 'automatic' },
      'Connecting to Orion',
      ['Open Machines'],
    ],
    [
      'provisioning',
      { kind: 'degraded', situation: 'provisioning', recovery: 'automatic' },
      'Preparing Orion',
      ['Open Machines'],
    ],
    [
      'handshaking',
      { kind: 'degraded', situation: 'handshaking', recovery: 'automatic' },
      'Preparing Orion',
      ['Open Machines'],
    ],
    [
      'attaching',
      { kind: 'degraded', situation: 'attaching', recovery: 'automatic' },
      'Opening Project on Orion',
      [],
    ],
    [
      'recovering',
      { kind: 'degraded', situation: 'recovering', recovery: 'automatic' },
      'Reconnecting to Orion',
      ['Retry now', 'Open Machines'],
    ],
    [
      'manual attention',
      { kind: 'degraded', situation: 'attention', recovery: 'manual' },
      'Orion needs attention',
      ['Retry', 'Open Machines'],
    ],
  ])('presents the SSH %s state', (_label, state, title, actionLabels) => {
    const presentation = classifyProjectAvailability({ host: ssh, state });
    expect(presentation?.title ?? null).toBe(title);
    expect(presentation?.actions.map((action) => action.label) ?? []).toEqual(actionLabels);
  });

  it.each<
    [semantic: keyof typeof issues, title: string, sshActions: string[], localActions: string[]]
  >([
    [
      'offline',
      'Orion is offline',
      ['Retry now', 'Open Machines'],
      ['Retry now', 'Open Diagnostics'],
    ],
    [
      'connection-failed',
      'Could not connect to Orion',
      ['Retry now', 'Open Machines'],
      ['Retry now', 'Open Diagnostics'],
    ],
    [
      'daemon-start-failed',
      "Could not start Orion's workspace server",
      ['Retry now', 'Open Machines'],
      ['Retry now', 'Open Diagnostics'],
    ],
    [
      'artifact-download-failed',
      'Could not download the workspace server',
      ['Retry', 'Open Machines'],
      ['Retry', 'Open Diagnostics'],
    ],
    [
      'install-failed',
      'Could not install the workspace server',
      ['Retry', 'Open Machines'],
      ['Retry', 'Open Diagnostics'],
    ],
    ['unsupported-platform', 'Orion is not supported', ['Open Machines'], ['Open Diagnostics']],
    [
      'protocol-upgrade-client',
      'Update Emdash to use this Project',
      ['Update Emdash'],
      ['Update Emdash'],
    ],
    [
      'protocol-upgrade-server',
      "Update Orion's workspace server",
      ['Open Machines', 'Retry'],
      ['Open Diagnostics', 'Retry'],
    ],
    [
      'runtime-unavailable',
      "Orion's workspace server is unavailable",
      ['Retry now', 'Open Machines'],
      ['Retry now', 'Open Diagnostics'],
    ],
    ['not-configured', 'Orion is not configured', ['Configure Machine'], ['Configure Runtime']],
    [
      'host-identity-lost',
      'This Project is no longer linked to a Machine',
      ['Relink Project', 'Remove Project'],
      ['Relink Project', 'Remove Project'],
    ],
    ['attachment-unavailable', 'Opening Project on Orion', [], []],
    ['repository-missing', 'Repository is missing', ['Retry'], ['Retry']],
    [
      'repository-unavailable',
      'Repository is unavailable',
      ['Retry', 'Open Machines'],
      ['Retry', 'Open Diagnostics'],
    ],
    [
      'unexpected',
      'Project access failed',
      ['Retry', 'Open Machines'],
      ['Retry', 'Open Diagnostics'],
    ],
    ['project-missing', '', [], []],
  ])(
    'presents %s without leaking lower-level data',
    (semantic, sshTitle, sshActions, localActions) => {
      const state = stateForIssue(issues[semantic]);
      const sshPresentation = classifyProjectAvailability({ host: ssh, state });
      const localPresentation = classifyProjectAvailability({ host: local, state });

      if (semantic === 'project-missing') {
        expect(sshPresentation).toBeNull();
        expect(localPresentation).toBeNull();
        return;
      }

      expect(sshPresentation?.title).toBe(sshTitle);
      expect(sshPresentation?.actions.map((action) => action.label)).toEqual(sshActions);
      expect(localPresentation?.actions.map((action) => action.label)).toEqual(localActions);
      expect(JSON.stringify({ sshPresentation, localPresentation })).not.toMatch(
        /connection-private-id|project-private-id|\/private\/|raw lower-level|raw filesystem|raw provider/
      );
      expect(JSON.stringify(localPresentation)).not.toMatch(/SSH|Machine|Open Machines|Connect/);
    }
  );

  it.each<[semantic: keyof typeof issues, title: string]>([
    ['offline', 'Local runtime is unavailable'],
    ['connection-failed', 'Local runtime connection failed'],
    ['daemon-start-failed', 'Local runtime could not start'],
    ['artifact-download-failed', 'Local runtime download failed'],
    ['install-failed', 'Local runtime installation failed'],
    ['unsupported-platform', 'This platform is not supported'],
    ['protocol-upgrade-client', 'Update Emdash to use this Project'],
    ['protocol-upgrade-server', 'Update the local runtime'],
    ['runtime-unavailable', 'Local runtime is unavailable'],
    ['not-configured', 'Local runtime is not configured'],
    ['host-identity-lost', 'This Project lost its local runtime link'],
    ['attachment-unavailable', 'Opening Project locally'],
    ['repository-missing', 'Repository is missing'],
    ['repository-unavailable', 'Repository is unavailable'],
    ['unexpected', 'Project access failed'],
    ['project-missing', ''],
  ])('uses exact local-only title copy for %s', (semantic, title) => {
    const presentation = classifyProjectAvailability({
      host: local,
      state: stateForIssue(issues[semantic]),
    });
    expect(presentation?.title ?? '').toBe(title);
  });

  it('uses exact local-only copy for unavailable runtime states', () => {
    const presentation = classifyProjectAvailability({
      host: local,
      state: { kind: 'degraded', situation: 'offline', recovery: 'automatic' },
    });

    expect(presentation?.title).toBe('Local runtime is unavailable');
    expect(presentation?.actions).toEqual([{ kind: 'retry', label: 'Retry' }]);
    expect(JSON.stringify(presentation)).not.toMatch(/SSH|Machine|Open Machines|Connect/);
  });
});

describe('projectLiveActionDisabledReason', () => {
  const state: ProjectHostAccessState = {
    kind: 'degraded',
    situation: 'offline',
    recovery: 'automatic',
  };

  it('uses exact SSH Machine copy', () => {
    expect(
      projectLiveActionDisabledReason({
        host: { kind: 'ssh', machineName: 'Orion' },
        state,
      })
    ).toBe('Live actions are unavailable while Orion is offline.');
  });

  it('uses exact local runtime copy without Machine language', () => {
    expect(projectLiveActionDisabledReason({ host: { kind: 'local' }, state })).toBe(
      'Live actions are unavailable while this Project is unavailable on this device.'
    );
  });
});

function stateForIssue(issue: ProjectAttachmentError): ProjectHostAccessState {
  const classification = classifyProjectAttachmentIssue(issue);
  if (issue.type === 'attachment-unavailable') {
    return {
      kind: 'degraded',
      situation: 'attaching',
      recovery: 'automatic',
      issue,
    };
  }
  return {
    kind: 'degraded',
    situation: classification.recovery === 'automatic' ? 'recovering' : 'attention',
    recovery: classification.recovery === 'dispose-context' ? 'blocked' : classification.recovery,
    issue,
  };
}
