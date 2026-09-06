import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { gitFilePathSchema } from '@emdash/core/runtimes/git/api';
import { z } from 'zod';
import { defineMemento } from '@core/primitives/mementos/api';
import { taskSubject } from './subject';

export const terminalDrawerActiveItemSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('terminal'), id: z.string() }),
  z.object({ kind: z.literal('script'), id: z.string() }),
]);
export type TerminalDrawerActiveItem = z.infer<typeof terminalDrawerActiveItemSchema>;

const taskChromeV1Schema = z.object({
  version: z.literal('1'),
  sidebarTab: z.enum(['conversations', 'changes', 'files', 'analysis']),
  sidebarCollapsed: z.boolean(),
  terminalDrawerOpen: z.boolean(),
});

export const taskChromeSchema = defineVersionedSchema().initial('1', taskChromeV1Schema).build();
export type TaskChromeState = typeof taskChromeSchema.Type;

export const taskChromeMemento = defineMemento({
  id: 'tasks.chrome',
  subject: taskSubject,
  schema: taskChromeSchema,
  default: {
    version: '1' as const,
    sidebarTab: 'conversations' as const,
    sidebarCollapsed: true,
    terminalDrawerOpen: false,
  },
});

const taskTerminalSelectionV1Schema = z.object({
  version: z.literal('1'),
  activeItem: terminalDrawerActiveItemSchema.optional(),
  tabOrder: z.array(z.string()),
  activeTabId: z.string().optional(),
});

export const taskTerminalSelectionSchema = defineVersionedSchema()
  .initial('1', taskTerminalSelectionV1Schema)
  .build();
export type TaskTerminalSelectionState = typeof taskTerminalSelectionSchema.Type;

export const taskTerminalSelectionMemento = defineMemento({
  id: 'tasks.terminal-selection',
  subject: taskSubject,
  schema: taskTerminalSelectionSchema,
  default: {
    version: '1' as const,
    tabOrder: [],
  },
});

const taskEditorTreeV1Schema = z.object({
  version: z.literal('1'),
  expandedPaths: z.array(z.string()),
});

export const taskEditorTreeSchema = defineVersionedSchema()
  .initial('1', taskEditorTreeV1Schema)
  .build();
export type TaskEditorTreeState = typeof taskEditorTreeSchema.Type;

export const taskEditorTreeMemento = defineMemento({
  id: 'tasks.editor-tree',
  subject: taskSubject,
  schema: taskEditorTreeSchema,
  default: {
    version: '1' as const,
    expandedPaths: [],
  },
});

const changesExpandedSectionsSchema = z.object({
  unstaged: z.boolean(),
  staged: z.boolean(),
  pullRequests: z.boolean(),
});

const taskDiffPreferencesV1Schema = z.object({
  version: z.literal('1'),
  diffStyle: z.enum(['unified', 'split']),
  commitAction: z.enum(['commit', 'commit-push', 'commit-pr']).nullable(),
  prTab: z.enum(['files', 'commits', 'checks']),
  // Changes-panel section expansion. Absent until the first git load seeds
  // it (ChangesViewStore keeps "never set" semantics); optional-on-v1 so
  // older app versions still parse documents written by newer ones.
  expandedSections: changesExpandedSectionsSchema.optional(),
});

export const taskDiffPreferencesSchema = defineVersionedSchema()
  .initial('1', taskDiffPreferencesV1Schema)
  .build();
export type TaskDiffPreferencesState = typeof taskDiffPreferencesSchema.Type;

export const taskDiffPreferencesMemento = defineMemento({
  id: 'tasks.diff-preferences',
  subject: taskSubject,
  schema: taskDiffPreferencesSchema,
  default: {
    version: '1' as const,
    diffStyle: 'unified' as const,
    commitAction: null,
    prTab: 'files' as const,
  },
});

const taskPanelLayoutsV1Schema = z.object({
  version: z.literal('1'),
  // Serialized panel layouts keyed by the react-resizable-panels internal
  // storage key (`react-resizable-panels:${id}[:${panelIds}]`).
  layouts: z.record(z.string(), z.string()),
});

export const taskPanelLayoutsSchema = defineVersionedSchema()
  .initial('1', taskPanelLayoutsV1Schema)
  .build();
export type TaskPanelLayoutsState = typeof taskPanelLayoutsSchema.Type;

export const taskPanelLayoutsMemento = defineMemento({
  id: 'tasks.panel-layouts',
  subject: taskSubject,
  schema: taskPanelLayoutsSchema,
  default: {
    version: '1' as const,
    layouts: {},
  },
});

/**
 * Panel id for one split-pane group inside the task-main split. Split-pane
 * sizes persist through the shared `tasks.panel-layouts` storage like every
 * other resizable surface; the library derives the storage entry key from
 * these ids (`react-resizable-panels:${groupId}:${panelIds...}`), so entries
 * are keyed by the (restart-stable) pane-group id combination.
 */
export function splitPanePanelId(paneGroupId: string): string {
  return `pane:${paneGroupId}`;
}

const gitRemoteSchema = z.object({
  name: z.string(),
  url: z.string(),
});

const gitBranchRefSchema = z.union([
  z.object({
    type: z.literal('local'),
    branch: z.string(),
    remote: gitRemoteSchema.optional(),
  }),
  z.object({
    type: z.literal('remote'),
    branch: z.string(),
    remote: gitRemoteSchema,
  }),
]);

const gitObjectRefSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('branch'), branch: gitBranchRefSchema }),
  z.object({ kind: z.literal('commit'), sha: z.string() }),
  z.object({ kind: z.literal('tag'), name: z.string() }),
]);

export const taskActiveFileSchema = z.object({
  path: gitFilePathSchema,
  type: z.enum(['disk', 'git']),
  group: z.enum(['disk', 'staged', 'git', 'pr']),
  originalRef: gitObjectRefSchema,
  modifiedRef: gitObjectRefSchema.optional(),
  prNumber: z.number().optional(),
  prBaseOid: z.string().optional(),
  prHeadOid: z.string().optional(),
  commitOriginalSha: z.string().nullable().optional(),
  commitModifiedSha: z.string().optional(),
});

export type TaskActiveFile = z.infer<typeof taskActiveFileSchema>;
export type ActiveFile = TaskActiveFile;

const taskDiffSelectionV1Schema = z.object({
  version: z.literal('1'),
  activeFile: taskActiveFileSchema.optional(),
});

export const taskDiffSelectionSchema = defineVersionedSchema()
  .initial('1', taskDiffSelectionV1Schema)
  .build();
export type TaskDiffSelectionState = typeof taskDiffSelectionSchema.Type;

export const taskDiffSelectionMemento = defineMemento({
  id: 'tasks.diff-selection',
  subject: taskSubject,
  schema: taskDiffSelectionSchema,
  default: {
    version: '1' as const,
  },
});

const browserSessionSchema = z.object({
  browserId: z.string(),
  projectId: z.string(),
  workspaceId: z.string(),
  taskId: z.string(),
  profileId: z.string(),
  partition: z.string(),
  currentUrl: z.string(),
  title: z.string(),
  faviconUrl: z.string().optional(),
  isLoading: z.boolean(),
  canGoBack: z.boolean(),
  canGoForward: z.boolean(),
  zoomFactor: z.number(),
  loadError: z
    .object({
      code: z.number().optional(),
      description: z.string(),
      url: z.string().optional(),
    })
    .optional(),
  createdAt: z.number(),
  updatedAt: z.number(),
});

export const tabDescriptorSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('conversation'),
    tabId: z.string(),
    conversationId: z.string(),
    isPreview: z.boolean(),
  }),
  z.object({
    kind: z.literal('acp-chat'),
    tabId: z.string(),
    conversationId: z.string(),
    isPreview: z.boolean(),
  }),
  z.object({
    kind: z.literal('file'),
    tabId: z.string(),
    path: z.string(),
    isPreview: z.boolean(),
  }),
  z.object({
    kind: z.literal('cad'),
    tabId: z.string(),
    path: z.string(),
    workspacePath: z.string(),
    browserId: z.string(),
    session: browserSessionSchema,
    chatOpen: z.boolean().optional(),
    workspaceMode: z
      .enum([
        '3d',
        '2d',
        'files',
        'drawing',
        'source',
        'parameters',
        'analysis',
        'bom',
        'motion',
        'instructions',
      ])
      .optional(),
    isPreview: z.boolean(),
  }),
  z.object({
    kind: z.literal('browser'),
    tabId: z.string(),
    browserId: z.string(),
    session: browserSessionSchema,
    isPreview: z.boolean(),
  }),
  z.object({
    kind: z.literal('terminal'),
    tabId: z.string(),
    terminalId: z.string(),
    isPreview: z.boolean(),
  }),
  z.object({
    kind: z.literal('diff'),
    tabId: z.string(),
    path: gitFilePathSchema,
    diffGroup: z.enum(['disk', 'staged', 'git', 'pr']),
    originalRef: gitObjectRefSchema,
    modifiedRef: gitObjectRefSchema.optional(),
    prNumber: z.number().optional(),
    prBaseOid: z.string().optional(),
    prHeadOid: z.string().optional(),
    commitOriginalSha: z.string().nullable().optional(),
    commitModifiedSha: z.string().optional(),
    status: z.enum(['added', 'modified', 'deleted', 'renamed', 'conflicted']).optional(),
    isPreview: z.boolean(),
  }),
]);
export type TabDescriptor = z.infer<typeof tabDescriptorSchema>;

export const taskPaneLayoutSnapshotSchema = z.object({
  groups: z
    .array(
      z.object({
        groupId: z.string().min(1),
        tabManager: z.object({
          tabs: z.array(tabDescriptorSchema),
          activeTabId: z.string().optional(),
        }),
      })
    )
    .min(1),
  activeGroupId: z.string().min(1),
});

export type TaskPaneLayoutSnapshot = z.infer<typeof taskPaneLayoutSnapshotSchema>;
export type TabGroupsSnapshot = TaskPaneLayoutSnapshot;
export type TabManagerSnapshot = TaskPaneLayoutSnapshot['groups'][number]['tabManager'];

const taskPaneLayoutV1Schema = z.object({
  version: z.literal('1'),
  ...taskPaneLayoutSnapshotSchema.shape,
  // v1 stored split-pane sizes inside the snapshot; v2 moved them onto the
  // shared panel-layouts storage (spec: pane-layout ownership).
  paneSizes: z.array(z.number()),
});

const taskPaneLayoutV2Schema = z.object({
  version: z.literal('2'),
  ...taskPaneLayoutSnapshotSchema.shape,
});

export const taskPaneLayoutSchema = defineVersionedSchema()
  .initial('1', taskPaneLayoutV1Schema)
  // Old paneSizes are abandoned, not migrated (spec: one-time layout reset).
  .version('2', taskPaneLayoutV2Schema, ({ paneSizes: _paneSizes, ...v1 }) => ({
    ...v1,
    version: '2' as const,
  }))
  .build();
export type TaskPaneLayoutState = typeof taskPaneLayoutSchema.Type;

export const taskPaneLayoutMemento = defineMemento({
  id: 'tasks.pane-layout',
  subject: taskSubject,
  schema: taskPaneLayoutSchema,
  default: {
    version: '2' as const,
    groups: [
      {
        groupId: 'default',
        tabManager: {
          tabs: [],
          activeTabId: undefined,
        },
      },
    ],
    activeGroupId: 'default',
  },
});
