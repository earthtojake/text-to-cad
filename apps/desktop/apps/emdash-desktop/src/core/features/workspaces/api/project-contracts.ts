import { defineContract, liveModel, liveState, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import type { ProjectSettingsLoadResult } from '@core/primitives/project-settings/api';
import type {
  HostWorkspaceGroupsData,
  MeasureProjectWorkspacesInput,
  MeasureProjectWorkspacesResult,
  ProjectWorkspaceActionSummary,
} from '@core/primitives/workspaces/api';

export const projectSettingsDomain = 'projectSettings' as const;

export const projectSettingsContract = defineContract({
  getSettings: procedure({
    input: z.object({ workspaceId: z.string() }),
    output: z.custom<ProjectSettingsLoadResult>(),
  }),
});

export const projectWorkspacesDomain = 'projectWorkspaces' as const;

/**
 * Mirror-served workspace reads (planning ticket 09): the live model is a DB read
 * poked by app-db changes — the registry sync keeps the mirror fresh, so no read here
 * ever scans a host. Disk usage stays an on-demand measurement.
 */
export const projectWorkspacesContract = defineContract({
  /** Workspace grouping: one group per project on the host, live from the mirror. */
  workspaceGroups: liveModel({
    key: z.object({ hostKey: z.string() }),
    states: {
      list: liveState({ data: z.custom<HostWorkspaceGroupsData>() }),
    },
  }),
  measureProjectWorkspaces: procedure({
    input: z.custom<MeasureProjectWorkspacesInput>(),
    output: z.custom<MeasureProjectWorkspacesResult>(),
  }),
  deleteProjectWorkspaces: procedure({
    input: z.object({
      projectId: z.string(),
      paths: z.array(z.string()),
      deleteConversations: z.boolean().optional(),
    }),
    output: z.custom<ProjectWorkspaceActionSummary>(),
  }),
});
