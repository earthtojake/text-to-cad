import { pokeChannel } from '@emdash/wire/state';

type Match<T> = (payload: T) => boolean;

export type TaskPoke = {
  projectId?: string;
  taskId?: string;
};

export type ConversationPoke = {
  projectId?: string;
  taskId?: string;
};

export type WorkspacePoke = {
  projectId?: string;
  taskId?: string;
  workspaceId?: string;
};

export type ProjectPoke = {
  projectId?: string;
};

export const appDbPokes = {
  tasks: pokeChannel<TaskPoke>('app-db:tasks'),
  conversations: pokeChannel<ConversationPoke>('app-db:conversations'),
  workspaces: pokeChannel<WorkspacePoke>('app-db:workspaces'),
  projects: pokeChannel<ProjectPoke>('app-db:projects'),
};

export function matchProject(projectId: string): Match<{ projectId?: string }> {
  return (payload) => payload.projectId === undefined || payload.projectId === projectId;
}
