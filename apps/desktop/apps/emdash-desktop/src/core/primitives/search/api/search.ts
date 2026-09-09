export type PaletteEntityKind = 'task' | 'project' | 'conversation';

export interface SearchItem {
  kind: PaletteEntityKind;
  id: string;
  projectId: string | null;
  taskId: string | null;
  title: string;
  subtitle: string;
  score: number;
}

export interface PaletteEntitySearchQuery {
  kind: PaletteEntityKind;
  query: string;
  context?: {
    projectId?: string;
    taskId?: string;
    workspaceId?: string;
  };
  limit?: number;
}

export interface WorkspaceFileSearchQuery {
  workspaceId: string;
  query: string;
  limit?: number;
}

export interface WorkspaceFileHit {
  path: string;
  filename: string;
}
