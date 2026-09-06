import { isRuntimeResolveError } from '@emdash/core/primitives/runtime-resolution/api';
import type { ProjectAttachmentError } from '@core/features/projects/api/attachments';

export type ProjectIssueRecovery = 'automatic' | 'manual' | 'blocked' | 'dispose-context';

export function projectAttachmentIssueRecovery(
  issue: ProjectAttachmentError
): ProjectIssueRecovery {
  if (isRuntimeResolveError(issue)) {
    if (issue.type === 'not-configured' || issue.type === 'host-identity-lost') return 'blocked';
    switch (issue.reason) {
      case 'offline':
      case 'connection-failed':
      case 'daemon-start-failed':
      case 'runtime-unavailable':
        return 'automatic';
      case 'artifact-download-failed':
      case 'install-failed':
        return 'manual';
      case 'unsupported-platform':
      case 'protocol-upgrade-client':
      case 'protocol-upgrade-server':
        return 'blocked';
    }
  }
  switch (issue.type) {
    case 'attachment-unavailable':
      return 'automatic';
    case 'repository-missing':
    case 'repository-unavailable':
    case 'unexpected':
      return 'manual';
    case 'project-missing':
      return 'dispose-context';
  }
}
