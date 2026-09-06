import { isRuntimeResolveError } from '@emdash/core/primitives/runtime-resolution/api';
import type { RuntimeUnavailableReason } from '@emdash/core/primitives/runtime-resolution/api';
import {
  PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
  type ProjectAttachmentError,
} from '@core/features/projects/api/attachments';
import {
  projectAttachmentIssueRecovery,
  type ProjectIssueRecovery,
} from '@core/features/projects/api/browser/project-attachment-recovery';
import type { ProjectHostAccessState } from '@core/features/projects/api/browser/stores/project-context';

export const DEFAULT_PROJECT_LIVE_ACTION_DISABLED_REASON = PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE;

export type ProjectAvailabilitySemantic =
  | RuntimeUnavailableReason
  | Exclude<ProjectAttachmentError['type'], 'host-unavailable'>;

export type ProjectCorrectiveAction =
  | 'retry'
  | 'diagnostics'
  | 'update-client'
  | 'configure'
  | 'relink-project'
  | 'remove-project';

export type ProjectAttachmentIssueClassification = {
  semantic: ProjectAvailabilitySemantic;
  recovery: ProjectIssueRecovery;
  correctiveActions: ProjectCorrectiveAction[];
};

export function classifyProjectAttachmentIssue(
  issue: ProjectAttachmentError
): ProjectAttachmentIssueClassification {
  const semantic = isRuntimeResolveError(issue)
    ? issue.type === 'host-unavailable'
      ? issue.reason
      : issue.type
    : issue.type;
  return {
    semantic,
    recovery: projectAttachmentIssueRecovery(issue),
    correctiveActions: correctiveActionsFor(semantic),
  };
}

export type ProjectAvailabilityAction = {
  kind:
    | 'connect'
    | 'retry'
    | 'diagnostics'
    | 'update-client'
    | 'configure'
    | 'relink-project'
    | 'remove-project';
  label: string;
};

export type ProjectAvailabilityPresentation = {
  severity: 'info' | 'warning' | 'error';
  announcement: 'polite' | 'assertive';
  title: string;
  detail: string;
  progress: boolean;
  actions: ProjectAvailabilityAction[];
};

export type ProjectAvailabilityHost = { kind: 'local' } | { kind: 'ssh'; machineName?: string };

export function classifyProjectAvailability({
  host,
  state,
}: {
  host: ProjectAvailabilityHost;
  state: ProjectHostAccessState;
}): ProjectAvailabilityPresentation | null {
  if (state.kind === 'ready') return null;
  const machineName = host.kind === 'ssh' ? host.machineName?.trim() || 'Machine' : undefined;

  switch (state.situation) {
    case 'suspended':
      return offlinePresentation(host, machineName);
    case 'connecting':
      return {
        severity: 'info',
        announcement: 'polite',
        title: host.kind === 'local' ? 'Preparing local runtime' : `Connecting to ${machineName}`,
        detail:
          host.kind === 'local'
            ? 'The Project stays open while local services start.'
            : 'The Project stays open while the SSH connection is established.',
        progress: true,
        actions: host.kind === 'ssh' ? [action('diagnostics', 'Open Machines')] : [],
      };
    case 'provisioning':
    case 'handshaking':
      return {
        severity: 'info',
        announcement: 'polite',
        title: host.kind === 'local' ? 'Preparing local runtime' : `Preparing ${machineName}`,
        detail:
          host.kind === 'local'
            ? 'The Project stays open while local services start.'
            : 'SSH is connected. The workspace server is starting.',
        progress: true,
        actions: host.kind === 'ssh' ? [action('diagnostics', 'Open Machines')] : [],
      };
    case 'attaching':
      return {
        severity: 'info',
        announcement: 'polite',
        title:
          host.kind === 'local' ? 'Opening Project locally' : `Opening Project on ${machineName}`,
        detail:
          host.kind === 'local'
            ? 'The local runtime is ready. Live Project features will be available shortly.'
            : 'The Machine is ready. Live Project features will be available shortly.',
        progress: true,
        actions: [],
      };
    case 'offline':
    case 'recovering':
    case 'attention':
      break;
  }

  if (state.issue) {
    const issue = classifyProjectAttachmentIssue(state.issue);
    if (issue.recovery === 'dispose-context') return null;
    return issuePresentation(host, machineName, state, issue);
  }
  if (state.situation === 'offline') return offlinePresentation(host, machineName);
  if (state.situation === 'recovering') {
    return {
      severity: 'warning',
      announcement: 'polite',
      title: host.kind === 'local' ? 'Recovering local runtime' : `Reconnecting to ${machineName}`,
      detail: 'Automatic recovery is in progress. Project data remains available.',
      progress: true,
      actions: recoveryActions(host, state.recovery, ['retry', 'diagnostics']),
    };
  }
  return {
    severity: 'error',
    announcement: 'assertive',
    title:
      host.kind === 'local' ? 'Local runtime needs attention' : `${machineName} needs attention`,
    detail: 'Project data remains available. Correct the problem, then retry.',
    progress: false,
    actions: recoveryActions(
      host,
      state.recovery,
      state.recovery === 'blocked' ? ['diagnostics'] : ['retry', 'diagnostics']
    ),
  };
}

export function projectLiveActionDisabledReason({
  host,
  state,
}: {
  host: ProjectAvailabilityHost;
  state: ProjectHostAccessState;
}): string | null {
  if (state.kind === 'ready') return null;
  if (host.kind === 'local') {
    return 'Live actions are unavailable while this Project is unavailable on this device.';
  }
  const machineName = host.machineName?.trim() || 'this Machine';
  if (state.situation === 'offline' || state.situation === 'suspended') {
    return `Live actions are unavailable while ${machineName} is offline.`;
  }
  const presentation = classifyProjectAvailability({ host, state });
  return presentation
    ? `Live actions are unavailable. ${presentation.title}.`
    : 'Live actions are unavailable for this Project.';
}

type IssuePresentationDescriptor = {
  correctiveActions: readonly ProjectCorrectiveAction[];
  title: (host: ProjectAvailabilityHost, machineName: string | undefined) => string;
  detail?: (host: ProjectAvailabilityHost) => string;
};

const issuePresentationDescriptors: Record<
  ProjectAvailabilitySemantic,
  IssuePresentationDescriptor
> = {
  offline: {
    correctiveActions: ['retry', 'diagnostics'],
    title: (host, machineName) =>
      host.kind === 'local' ? 'Local runtime is unavailable' : `${machineName} is offline`,
  },
  'connection-failed': {
    correctiveActions: ['retry', 'diagnostics'],
    title: (host, machineName) =>
      host.kind === 'local'
        ? 'Local runtime connection failed'
        : `Could not connect to ${machineName}`,
  },
  'daemon-start-failed': {
    correctiveActions: ['retry', 'diagnostics'],
    title: (host, machineName) =>
      host.kind === 'local'
        ? 'Local runtime could not start'
        : `Could not start ${machineName}'s workspace server`,
  },
  'artifact-download-failed': {
    correctiveActions: ['retry', 'diagnostics'],
    title: (host) =>
      host.kind === 'local'
        ? 'Local runtime download failed'
        : 'Could not download the workspace server',
  },
  'install-failed': {
    correctiveActions: ['retry', 'diagnostics'],
    title: (host) =>
      host.kind === 'local'
        ? 'Local runtime installation failed'
        : 'Could not install the workspace server',
  },
  'unsupported-platform': {
    correctiveActions: ['diagnostics'],
    title: (host, machineName) =>
      host.kind === 'local' ? 'This platform is not supported' : `${machineName} is not supported`,
    detail: (host) =>
      host.kind === 'local'
        ? 'Review system details before moving this Project to a supported computer.'
        : 'Review Machine details before moving this Project to a supported Machine.',
  },
  'protocol-upgrade-client': {
    correctiveActions: ['update-client'],
    title: () => 'Update Hardcore to use this project',
    detail: () => 'Install the latest Hardcore version to restore project access.',
  },
  'protocol-upgrade-server': {
    correctiveActions: ['diagnostics', 'retry'],
    title: (host, machineName) =>
      host.kind === 'local'
        ? 'Update the local runtime'
        : `Update ${machineName}'s workspace server`,
    detail: () => 'Update the workspace server, then retry Project access.',
  },
  'runtime-unavailable': {
    correctiveActions: ['retry', 'diagnostics'],
    title: (host, machineName) =>
      host.kind === 'local'
        ? 'Local runtime is unavailable'
        : `${machineName}'s workspace server is unavailable`,
  },
  'not-configured': {
    correctiveActions: ['configure'],
    title: (host, machineName) =>
      host.kind === 'local'
        ? 'Local runtime is not configured'
        : `${machineName} is not configured`,
    detail: (host) =>
      host.kind === 'local'
        ? 'Configure the local runtime to restore live features.'
        : 'Configure this Machine to restore live features.',
  },
  'host-identity-lost': {
    correctiveActions: ['relink-project', 'remove-project'],
    title: (host) =>
      host.kind === 'local'
        ? 'This Project lost its local runtime link'
        : 'This Project is no longer linked to a Machine',
    detail: (host) =>
      host.kind === 'local'
        ? 'Relink this project to a local runtime or remove it from Hardcore.'
        : 'Relink this project to a machine or remove it from Hardcore.',
  },
  'attachment-unavailable': {
    correctiveActions: [],
    title: (host, machineName) =>
      host.kind === 'local' ? 'Opening Project locally' : `Opening Project on ${machineName}`,
  },
  'project-missing': {
    correctiveActions: [],
    title: () => '',
  },
  'repository-missing': {
    correctiveActions: ['retry'],
    title: () => 'Repository is missing',
    detail: () => 'Restore the repository or relink the Project, then retry.',
  },
  'repository-unavailable': {
    correctiveActions: ['retry', 'diagnostics'],
    title: () => 'Repository is unavailable',
  },
  unexpected: {
    correctiveActions: ['retry', 'diagnostics'],
    title: () => 'Project access failed',
  },
};

function correctiveActionsFor(semantic: ProjectAvailabilitySemantic): ProjectCorrectiveAction[] {
  return [...issuePresentationDescriptors[semantic].correctiveActions];
}

function offlinePresentation(
  host: ProjectAvailabilityHost,
  machineName: string | undefined
): ProjectAvailabilityPresentation {
  return {
    severity: 'warning',
    announcement: 'polite',
    title: host.kind === 'local' ? 'Local runtime is unavailable' : `${machineName} is offline`,
    detail: 'Project data remains available. Live features will resume when access returns.',
    progress: false,
    actions: [host.kind === 'local' ? action('retry', 'Retry') : action('connect', 'Connect')],
  };
}

function issuePresentation(
  host: ProjectAvailabilityHost,
  machineName: string | undefined,
  state: Extract<ProjectHostAccessState, { kind: 'degraded' }>,
  issue: Exclude<ProjectAttachmentIssueClassification, { recovery: 'dispose-context' }>
): ProjectAvailabilityPresentation {
  const recoveryContinues = state.recovery === 'automatic';
  const automaticExhausted = state.recovery === 'manual' && issue.recovery === 'automatic';
  return {
    severity: recoveryContinues ? 'warning' : 'error',
    announcement: recoveryContinues ? 'polite' : 'assertive',
    title: issueTitle(host, machineName, issue.semantic),
    detail: issueDetail(host, issue.semantic, recoveryContinues, automaticExhausted),
    progress: recoveryContinues,
    actions: recoveryActions(host, state.recovery, issue.correctiveActions),
  };
}

function issueTitle(
  host: ProjectAvailabilityHost,
  machineName: string | undefined,
  semantic: ProjectAvailabilitySemantic
): string {
  return issuePresentationDescriptors[semantic].title(host, machineName);
}

function issueDetail(
  host: ProjectAvailabilityHost,
  semantic: ProjectAvailabilitySemantic,
  recoveryContinues: boolean,
  automaticExhausted: boolean
): string {
  if (recoveryContinues) {
    return 'Automatic recovery will continue. Project data remains available.';
  }
  if (automaticExhausted) {
    return 'Automatic recovery stopped after six attempts. Retry when access is available.';
  }
  return (
    issuePresentationDescriptors[semantic].detail?.(host) ??
    'Project data remains available. Correct the problem, then retry.'
  );
}

function recoveryActions(
  host: ProjectAvailabilityHost,
  recovery: Extract<ProjectHostAccessState, { kind: 'degraded' }>['recovery'],
  correctiveActions: ProjectCorrectiveAction[]
): ProjectAvailabilityAction[] {
  return correctiveActions.map((corrective) => {
    switch (corrective) {
      case 'retry':
        return action('retry', recovery === 'automatic' ? 'Retry now' : 'Retry');
      case 'diagnostics':
        return action('diagnostics', host.kind === 'local' ? 'Open Diagnostics' : 'Open Machines');
      case 'update-client':
        return action('update-client', 'Update Hardcore');
      case 'configure':
        return action(
          'configure',
          host.kind === 'local' ? 'Configure Runtime' : 'Configure Machine'
        );
      case 'relink-project':
        return action('relink-project', 'Relink Project');
      case 'remove-project':
        return action('remove-project', 'Remove Project');
    }
  });
}

function action(kind: ProjectAvailabilityAction['kind'], label: string): ProjectAvailabilityAction {
  return { kind, label };
}
