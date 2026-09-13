import { makeAutoObservable, observable } from 'mobx';
import type { ProjectContextLifecycle } from '@core/features/projects/api/browser/stores/project-context';
import type { LocalProject, SshProject } from '@core/primitives/projects/api';

export type ProjectCreationStage = 'creating-repo' | 'cloning' | 'registering';

export type CreationStatus =
  | {
      kind: 'running';
      stage: ProjectCreationStage;
      progressMessage?: string;
      progressPercent?: number;
    }
  | { kind: 'failed'; stage: ProjectCreationStage; message: string };

export type ProjectMode = 'pick' | 'clone' | 'new';

/**
 * Container class — holds a stable reference in the ObservableMap across all
 * lifecycle transitions. Transitioning replaces each state's payload atomically.
 */
export class ProjectStore {
  state: 'unregistered' | 'registered';
  id: string;
  name: string | null;
  data: LocalProject | SshProject | null;
  createdAt: string;
  creation: CreationStatus | null;
  mode: ProjectMode | null;
  context: ProjectContextLifecycle | null = null;

  constructor(
    state: ProjectStore['state'],
    id: string,
    name: string | null,
    data: LocalProject | SshProject | null,
    creation: CreationStatus | null,
    mode: ProjectMode | null = null
  ) {
    this.state = state;
    this.id = id;
    this.name = name;
    this.data = data;
    this.createdAt = data?.createdAt ?? new Date().toISOString();
    this.creation = creation;
    this.mode = mode;
    makeAutoObservable(this, {
      creation: observable.ref,
      context: observable.ref,
    });
  }

  updateData(data: LocalProject | SshProject): void {
    if (!this.data) throw new Error(`Cannot update unregistered project ${this.id}`);
    if (data.id !== this.id) {
      throw new Error(`Cannot change project identity from ${this.id} to ${data.id}`);
    }
    if (data.type !== this.data.type) {
      throw new Error(
        `Cannot change project ${this.id} type from ${this.data.type} to ${data.type}`
      );
    }

    Object.assign(this.data, data);
    this.name = data.name;
    this.createdAt = data.createdAt;
  }

  register(data: LocalProject | SshProject): void {
    this.data = data;
    this.id = data.id;
    this.name = data.name;
    this.createdAt = data.createdAt;
    this.state = 'registered';
    this.creation = null;
    this.mode = null;
  }

  updateCreationProgress(
    stage: ProjectCreationStage,
    progress?: { message?: string; percent?: number }
  ): void {
    this.creation = {
      kind: 'running',
      stage,
      progressMessage: progress?.message,
      progressPercent: progress?.percent,
    };
  }

  failCreation(message: string): void {
    if (this.creation === null || this.creation.kind === 'failed') return;
    this.creation = { kind: 'failed', stage: this.creation.stage, message };
  }
}

export type UnregisteredProject = ProjectStore & {
  state: 'unregistered';
  id: string;
  name: string;
  creation: CreationStatus;
  mode: ProjectMode;
};

export type RegisteredProject = ProjectStore & {
  state: 'registered';
  data: LocalProject | SshProject;
};

export function isUnregisteredProject(p: ProjectStore): p is UnregisteredProject {
  return p.state === 'unregistered';
}

export function isRegisteredProject(p: ProjectStore): p is RegisteredProject {
  return p.state === 'registered';
}

export function createUnregisteredProject(
  id: string,
  name: string,
  creation: CreationStatus,
  mode: ProjectMode = 'pick'
): ProjectStore {
  return new ProjectStore('unregistered', id, name, null, creation, mode);
}

export function createRegisteredProject(data: LocalProject | SshProject): ProjectStore {
  return new ProjectStore('registered', data.id, data.name, data, null);
}
