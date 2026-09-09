import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { z } from 'zod';
import { defineMemento } from '@core/primitives/mementos/api';
import { projectSubject } from './subject';

export const projectTaskSortBySchema = z.enum(['created-at', 'updated-at', 'pr-status', 'unread']);
export type ProjectTaskSortBy = z.infer<typeof projectTaskSortBySchema>;

const projectViewV1Schema = z.object({
  version: z.literal('1'),
  activeView: z.enum(['tasks', 'pull-request', 'workspaces', 'settings']),
  taskViewTab: z.enum(['active', 'archived']),
  taskSortBy: projectTaskSortBySchema.optional(),
  selectedIssueProvider: z.string().optional(),
});

export const projectViewSchema = defineVersionedSchema().initial('1', projectViewV1Schema).build();

export type ProjectViewState = typeof projectViewSchema.Type;

export const projectViewMemento = defineMemento({
  id: 'projects.view',
  subject: projectSubject,
  schema: projectViewSchema,
  default: {
    version: '1' as const,
    activeView: 'tasks' as const,
    taskViewTab: 'active' as const,
  },
});

const workspaceChromeV1Schema = z.object({
  version: z.literal('1'),
  leftSidebarOpen: z.boolean(),
  // Zen mode is plain data inside the chrome document (spec §Chrome command
  // stores): `restore` snapshots the workspace fields zen overrides so exit
  // can put them back. It persists with the document — restarting in zen
  // resumes zen with a working restore.
  zen: z.object({
    active: z.boolean(),
    restore: z.object({ leftSidebarOpen: z.boolean().optional() }),
  }),
});

export const workspaceChromeSchema = defineVersionedSchema()
  .initial('1', workspaceChromeV1Schema)
  .build();
export type WorkspaceChromeState = typeof workspaceChromeSchema.Type;

export const workspaceChromeMemento = defineMemento({
  id: 'projects.workspace-chrome',
  subject: projectSubject,
  schema: workspaceChromeSchema,
  default: {
    version: '1' as const,
    leftSidebarOpen: true,
    zen: { active: false, restore: {} },
  },
});

const projectPanelLayoutsV1Schema = z.object({
  version: z.literal('1'),
  // Serialized panel layouts for workspace chrome surfaces, keyed by the
  // react-resizable-panels internal storage key
  // (`react-resizable-panels:${id}[:${panelIds}]`).
  layouts: z.record(z.string(), z.string()),
});

export const projectPanelLayoutsSchema = defineVersionedSchema()
  .initial('1', projectPanelLayoutsV1Schema)
  .build();
export type ProjectPanelLayoutsState = typeof projectPanelLayoutsSchema.Type;

export const projectPanelLayoutsMemento = defineMemento({
  id: 'projects.panel-layouts',
  subject: projectSubject,
  schema: projectPanelLayoutsSchema,
  default: {
    version: '1' as const,
    layouts: {},
  },
});
