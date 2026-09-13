import { runtimeHostUnavailable } from '@emdash/core/primitives/runtime-resolution/api';
import { err, ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import type { RemoteModel } from '@emdash/wire/state';
import { action, computed, makeObservable, observable } from 'mobx';
import type {
  projectsWireContract,
  ProjectAttachmentError,
  ProjectAttachmentState,
  ProjectRecoveryRequestError,
} from '@core/features/projects/api';
import {
  deriveProjectHostAccessState,
  type LiveActionAvailability,
  type ProjectContext as ProjectContextApi,
  type ProjectContextError,
  type ProjectHostAccess,
  type ProjectHostAccessState,
} from '@core/features/projects/api/browser/stores/project-context';
import type {
  HostObservation,
  ProjectHostObservation,
} from '@core/features/projects/api/host-observation';
import type { ProjectScopedStoreContext } from '@core/features/projects/contributions/project-stores';
import { projectSubject } from '@core/features/projects/contributions/subject';
import {
  createLayoutStorage,
  getMementoClient,
  type SubjectSpace,
} from '@core/primitives/mementos/browser';
import { projectHostRef, projectSchema, type Project } from '@core/primitives/projects/api';
import {
  ScopedStoreHost,
  type ScopedStoreContribution,
  type ScopedStoreToken,
  type ScopedStoreValue,
} from '@core/primitives/scoped-stores/browser';
import { observeReadableInAction } from '@core/primitives/wire/browser/mobx-readable';
import type { hostsContract, HostAvailabilityState } from '@core/services/hosts/api';

class HydratingProjectHostAccess implements ProjectHostAccess {
  availability: HostAvailabilityState | undefined;
  attachment: ProjectAttachmentState | undefined;
  private recoverRequest: (() => Promise<Result<void, ProjectRecoveryRequestError>>) | undefined;
  private recoveryRequest: Promise<Result<void, ProjectRecoveryRequestError>> | undefined;

  constructor(private readonly project: Project) {
    makeObservable(this, {
      attachment: observable.ref,
      availability: observable.ref,
      clear: action,
      liveAction: computed,
      state: computed,
    });
  }

  get state(): ProjectHostAccessState {
    const state = deriveProjectHostAccessState(this.availability, this.attachment);
    if (!state) throw new Error('Project context no longer exists');
    return state;
  }

  get liveAction(): LiveActionAvailability {
    const state = this.state;
    return state.kind === 'ready' ? { kind: 'enabled' } : { kind: 'disabled', state };
  }

  observe<T>(observation: HostObservation<T>): ProjectHostObservation<T> {
    if (observation.kind === 'never-observed') return { kind: 'unavailable' };
    return this.state.kind === 'ready'
      ? { kind: 'fresh', value: observation.value, observedAt: observation.observedAt }
      : { kind: 'stale', value: observation.value, observedAt: observation.observedAt };
  }

  requireLive(): Result<void, ProjectAttachmentError> {
    const host = projectHostRef(this.project);
    const availability = this.availability;
    if (!availability) {
      return err(runtimeHostUnavailable(host, 'offline', 'Host is offline'));
    }
    if (availability.kind === 'unavailable') {
      return err(availability.issue ?? runtimeHostUnavailable(host, 'offline', 'Host is offline'));
    }
    if (availability.kind === 'suspended') {
      return err(runtimeHostUnavailable(host, 'offline', 'Host is offline'));
    }
    if (availability.kind === 'preparing') {
      return err(
        availability.phase === 'connecting'
          ? runtimeHostUnavailable(host, 'connection-failed', 'Host connection is not ready')
          : runtimeHostUnavailable(host, 'runtime-unavailable', 'Host runtime is not ready')
      );
    }
    if (this.attachment?.kind === 'attached') return ok();
    if (this.attachment?.kind === 'absent' && this.attachment.lastFailure) {
      return err(this.attachment.lastFailure);
    }
    return err({
      type: 'attachment-unavailable',
      host,
      phase: this.attachment?.kind === 'attaching' ? 'attaching' : 'waiting',
    });
  }

  recover(): Promise<Result<void, ProjectRecoveryRequestError>> {
    if (this.recoveryRequest) return this.recoveryRequest;
    const request = this.recoverRequest?.();
    if (!request) {
      return Promise.resolve(err({ type: 'project-missing', projectId: this.project.id }));
    }
    this.recoveryRequest = request;
    void request.then(
      () => this.clearRecoveryRequest(request),
      () => this.clearRecoveryRequest(request)
    );
    return request;
  }

  bindRecovery(request: () => Promise<Result<void, ProjectRecoveryRequestError>>): void {
    this.recoverRequest = request;
  }

  clear(): void {
    this.availability = undefined;
    this.attachment = undefined;
    this.recoverRequest = undefined;
  }

  private clearRecoveryRequest(request: Promise<Result<void, ProjectRecoveryRequestError>>): void {
    if (this.recoveryRequest === request) this.recoveryRequest = undefined;
  }
}

export class ProjectContext implements ProjectContextApi {
  readonly host: ProjectHostAccess;
  private readonly space: SubjectSpace<'project'>;
  private readonly stores: ScopedStoreHost<ProjectScopedStoreContext>;
  private readonly mutableHost: HydratingProjectHostAccess;
  private readonly scope: Scope;
  private hostAccessScope: Scope | undefined;

  private constructor(
    readonly project: Project,
    space: SubjectSpace<'project'>,
    stores: ScopedStoreHost<ProjectScopedStoreContext>,
    host: HydratingProjectHostAccess
  ) {
    this.space = space;
    this.stores = stores;
    this.host = host;
    this.mutableHost = host;
    this.scope = createScope({ label: `project-context:${project.id}` });
    this.scope.add(async () => await releaseSpace(this.space));
    this.scope.add(() => this.stores.dispose());
    this.scope.add(async () => await this.releaseHostAccess());
  }

  get<Token extends ScopedStoreToken<unknown>>(token: Token): ScopedStoreValue<Token> {
    return this.stores.get(token);
  }

  createLayoutStorage(
    definition: Parameters<typeof createLayoutStorage<'project'>>[1]
  ): ReturnType<typeof createLayoutStorage<'project'>> {
    return createLayoutStorage(this.space, definition);
  }

  static async hydrate(
    record: unknown,
    contributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[]
  ): Promise<Result<ProjectContext, ProjectContextError>> {
    const parsed = projectSchema.safeParse(record);
    if (!parsed.success) {
      return err({
        type: 'invalid-project-record',
        message: parsed.error.message,
      });
    }

    const project = record as Project;
    const mementos = getMementoClient();
    let space: SubjectSpace<'project'>;
    try {
      space = mementos.subject(projectSubject({ projectId: project.id }));
    } catch (error) {
      return err(contextInitializationError('memento', error));
    }

    const host = new HydratingProjectHostAccess(project);
    let stores: ScopedStoreHost<ProjectScopedStoreContext>;
    try {
      stores = new ScopedStoreHost({ project, space, host }, contributions);
    } catch (error) {
      await releaseSpace(space);
      return err(contextInitializationError('scoped-stores', error));
    }

    try {
      await Promise.all([
        space.ready.catch((error: unknown) => {
          throw new ContextHydrationStageError('memento', error);
        }),
        stores.ready().catch((error: unknown) => {
          throw new ContextHydrationStageError('scoped-stores', error);
        }),
      ]);
      stores.activate();
    } catch (error) {
      stores.dispose();
      await releaseSpace(space);
      const failure =
        error instanceof ContextHydrationStageError
          ? error
          : new ContextHydrationStageError('scoped-stores', error);
      return err(contextInitializationError(failure.stage, failure.cause));
    }

    return ok(new ProjectContext(project, space, stores, host));
  }

  trackHostAccess(
    availabilityModel: RemoteModel<typeof hostsContract.availability>,
    attachmentModel: RemoteModel<typeof projectsWireContract.attachments>,
    recover: () => Promise<Result<void, ProjectRecoveryRequestError>> = () =>
      Promise.resolve(err({ type: 'project-missing', projectId: this.project.id })),
    onProjectMissing: () => void = () => {}
  ): void {
    if (this.scope.disposed) return;
    void this.releaseHostAccess();
    const accessScope = createScope({ label: `project-host-access:${this.project.id}` });
    const availabilityKey = { host: projectHostRef(this.project) };
    const attachmentKey = { projectId: this.project.id };
    const releaseAvailability = availabilityModel.retain(availabilityKey);
    let releaseAttachment: (() => void) | undefined;
    try {
      releaseAttachment = attachmentModel.retain(attachmentKey);
      const availability = availabilityModel(availabilityKey).states.state;
      const attachment = attachmentModel(attachmentKey).states.state;
      observeReadableInAction(
        availability,
        (snapshot) => {
          this.mutableHost.availability = snapshot.value;
        },
        { scope: accessScope, immediate: true }
      );
      let projectMissingReported = false;
      observeReadableInAction(
        attachment,
        (snapshot) => {
          if (
            snapshot.value.kind === 'absent' &&
            snapshot.value.lastFailure?.type === 'project-missing'
          ) {
            if (!projectMissingReported) {
              projectMissingReported = true;
              onProjectMissing();
            }
            return;
          }
          this.mutableHost.attachment = snapshot.value;
        },
        { scope: accessScope, immediate: true }
      );
      accessScope.add(releaseAvailability);
      accessScope.add(releaseAttachment);
      this.mutableHost.bindRecovery(recover);
      this.hostAccessScope = accessScope;
    } catch (error) {
      releaseAttachment?.();
      releaseAvailability();
      void accessScope.dispose();
      throw error;
    }
  }

  async dispose(): Promise<void> {
    await this.scope.dispose();
  }

  private async releaseHostAccess(): Promise<void> {
    const accessScope = this.hostAccessScope;
    this.hostAccessScope = undefined;
    this.mutableHost.clear();
    await accessScope?.dispose();
  }
}

class ContextHydrationStageError {
  constructor(
    readonly stage: 'memento' | 'scoped-stores',
    readonly cause: unknown
  ) {}
}

function contextInitializationError(
  stage: 'memento' | 'scoped-stores',
  error: unknown
): ProjectContextError {
  return {
    type: 'context-initialization-failed',
    stage,
    message: error instanceof Error ? error.message : String(error),
  };
}

async function releaseSpace(space: SubjectSpace<'project'>): Promise<void> {
  try {
    await space.release();
  } catch (error) {
    getMementoClient().reportError(error);
  }
}
