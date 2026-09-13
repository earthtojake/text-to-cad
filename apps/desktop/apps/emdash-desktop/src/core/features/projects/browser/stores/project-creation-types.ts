import type { Result } from '@emdash/shared';
import type { CreateProjectError, ProjectPlacementError } from '@core/primitives/projects/api';

interface BaseModeData {
  name: string;
  path: string;
}

export interface PickModeData extends BaseModeData {
  mode: 'pick';
  initGitRepository?: boolean;
  githubAccountId?: string;
}

export interface CloneModeData extends BaseModeData {
  mode: 'clone';
  repositoryUrl: string;
}

export interface NewModeData extends BaseModeData {
  mode: 'new';
  repositoryName: string;
  repositoryOwner: string;
  repositoryVisibility: 'public' | 'private';
  githubAccountId?: string;
}

export type ModeData = PickModeData | CloneModeData | NewModeData;

export type ProjectType = { type: 'local' } | { type: 'ssh'; connectionId: string };

export type ProjectCreationError =
  | CreateProjectError
  | ProjectPlacementError
  | { type: 'cancelled'; message: string }
  | { type: 'clone-failed'; message: string }
  | { type: 'repository-create-failed'; message: string }
  | { type: 'repository-response-incomplete'; message: string }
  | { type: 'initialize-failed'; message: string };

export type ProjectCreationCompletion = Result<void, ProjectCreationError>;

export type StartProjectCreationResult =
  | { kind: 'existing'; projectId: string }
  | { kind: 'creating'; projectId: string; completion: Promise<ProjectCreationCompletion> };

export interface StartProjectCreationOptions {
  id?: string;
}
