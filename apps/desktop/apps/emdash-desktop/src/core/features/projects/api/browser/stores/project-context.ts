import type { Result } from '@emdash/shared';
import type {
  ProjectAttachmentError,
  ProjectAttachmentState,
  ProjectRecoveryRequestError,
} from '@core/features/projects/api';
import { projectAttachmentIssueRecovery } from '@core/features/projects/api/browser/project-attachment-recovery';
import type { createLayoutStorage, MementoLayoutStorage } from '@core/primitives/mementos/browser';
import type { Project } from '@core/primitives/projects/api';
import type { ScopedStoreToken, ScopedStoreValue } from '@core/primitives/scoped-stores/browser';
import type { HostAvailabilityState } from '@core/services/hosts/api';
import type { HostObservation, ProjectHostObservation } from '../../host-observation';

export type ProjectContextError =
  | { type: 'invalid-project-record'; message: string }
  | {
      type: 'context-initialization-failed';
      stage: 'memento' | 'scoped-stores';
      message: string;
    };

export type ProjectContextLifecycle =
  | { kind: 'hydrating'; project: Project }
  | { kind: 'available'; context: ProjectContext }
  | {
      kind: 'failed';
      project: Project;
      error: ProjectContextError;
    };

export type ProjectHostAccessState =
  | { kind: 'ready'; hostGeneration: number }
  | {
      kind: 'degraded';
      situation:
        | 'offline'
        | 'connecting'
        | 'provisioning'
        | 'handshaking'
        | 'attaching'
        | 'recovering'
        | 'attention'
        | 'suspended';
      recovery: 'automatic' | 'manual' | 'blocked';
      issue?: ProjectAttachmentError;
      nextAttemptAt?: number;
    };

export type LiveActionAvailability =
  | { kind: 'enabled' }
  | { kind: 'disabled'; state: ProjectHostAccessState };

export interface ProjectHostAccess {
  readonly state: ProjectHostAccessState;
  readonly liveAction: LiveActionAvailability;
  observe<T>(observation: HostObservation<T>): ProjectHostObservation<T>;
  requireLive(): Result<void, ProjectAttachmentError>;
  recover(): Promise<Result<void, ProjectRecoveryRequestError>>;
}

export interface ProjectContext {
  readonly project: Project;
  readonly host: ProjectHostAccess;
  get<Token extends ScopedStoreToken<unknown>>(token: Token): ScopedStoreValue<Token>;
  createLayoutStorage(
    definition: Parameters<typeof createLayoutStorage<'project'>>[1]
  ): MementoLayoutStorage;
  dispose(): Promise<void>;
}

export function deriveProjectHostAccessState(
  availability: HostAvailabilityState | undefined,
  attachment: ProjectAttachmentState | undefined
): ProjectHostAccessState | null {
  if (!availability) {
    return { kind: 'degraded', situation: 'offline', recovery: 'automatic' };
  }
  if (availability.kind === 'suspended') {
    return { kind: 'degraded', situation: 'suspended', recovery: 'manual' };
  }
  if (availability.kind === 'preparing') {
    return {
      kind: 'degraded',
      situation: availability.phase,
      recovery: 'automatic',
    };
  }
  if (availability.kind === 'unavailable') {
    const issue = availability.issue;
    if (availability.recovery === 'eligible' || availability.recovery === 'waiting') {
      return {
        kind: 'degraded',
        situation: availability.recovery === 'waiting' ? 'recovering' : 'offline',
        recovery: 'automatic',
        ...(issue ? { issue } : {}),
        ...(availability.nextAttemptAt !== undefined
          ? { nextAttemptAt: availability.nextAttemptAt }
          : {}),
      };
    }
    return {
      kind: 'degraded',
      situation: 'attention',
      recovery: availability.recovery,
      ...(issue ? { issue } : {}),
    };
  }
  if (attachment?.kind === 'attached') {
    return { kind: 'ready', hostGeneration: availability.generation };
  }
  if (attachment?.kind !== 'absent' || !attachment.lastFailure) {
    return { kind: 'degraded', situation: 'attaching', recovery: 'automatic' };
  }
  const issue = attachment.lastFailure;
  const recovery = projectAttachmentIssueRecovery(issue);
  if (recovery === 'dispose-context') return null;
  if (recovery === 'automatic' && issue.type === 'attachment-unavailable') {
    return {
      kind: 'degraded',
      situation: 'attaching',
      recovery: 'automatic',
      issue,
    };
  }
  return {
    kind: 'degraded',
    situation: 'attention',
    recovery,
    issue,
  };
}
