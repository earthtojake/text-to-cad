import { z } from 'zod';
import type { AttachmentRef } from '../attachments';
import { attachmentRefSchema } from '../attachments';
import { planEntryInputSchema, type PlanEntryInput } from '../plan';
import type { ToolCallGroupKind, ToolStatus } from './tools';
import { toolCallGroupKindSchema, toolStatusSchema } from './tools';

export interface BaseToolCallItem {
  id: string;
  seq: number;
  toolCallId: string;
  title: string;
  status: ToolStatus;
  inputSummary?: string;
  /** Provider-reported text result, capped by the reducer; previewed where a row has room. */
  outputText?: string;
  /** Short failure reason when the provider reported the call as failed. */
  error?: string;
  /** Latest provider progress line while the call runs (MCP progress, for example). */
  progress?: string;
  parentToolCallId?: string;
  children?: ToolNode[];
  /** Runtime-owned image outputs produced by this tool call. */
  attachments?: AttachmentRef[];
}

export interface ExecuteToolCall extends BaseToolCallItem {
  kind: 'execute-tool-call';
  command?: string;
  outputText?: string;
  terminalId?: string;
}

export interface ReadToolCall extends BaseToolCallItem {
  kind: 'read-tool-call';
  path?: string;
  resource?: string;
}

export interface FileToolCallBase extends BaseToolCallItem {
  path: string;
}

export interface CreateFileToolCall extends FileToolCallBase {
  kind: 'create-file-tool-call';
  content: string;
}

export interface ModifyFileToolCall extends FileToolCallBase {
  kind: 'modify-file-tool-call';
  oldText: string;
  newText: string;
}

export interface DeleteFileToolCall extends FileToolCallBase {
  kind: 'delete-file-tool-call';
}

export interface SearchToolCall extends BaseToolCallItem {
  kind: 'search-tool-call';
  query: string;
  /** Search domain supplied by provider normalization when known. */
  scope?: 'web' | 'workspace';
  matchCount?: number;
}

export interface McpToolCall extends BaseToolCallItem {
  kind: 'mcp-tool-call';
  server?: string;
  tool: string;
}

export interface WebFetchToolCall extends BaseToolCallItem {
  kind: 'web-fetch-tool-call';
  url: string;
  pageTitle?: string;
}

export interface SpawnSubagentToolCall extends BaseToolCallItem {
  kind: 'spawn-subagent-tool-call';
  name: string;
  background?: boolean;
  agentId?: string;
}

export interface CreatePlanToolCall extends BaseToolCallItem {
  kind: 'create-plan-tool-call';
  planId: string;
  /** The plan as it stood when this turn last updated it; the live plan slice keeps moving. */
  entries?: PlanEntryInput[];
}

export interface UnknownToolCall extends BaseToolCallItem {
  kind: 'unknown-tool-call';
  toolKind: string | null;
  name: string;
}

export interface ToolGroup {
  kind: 'tool-group';
  id: string;
  seq: number;
  label: string;
  groupKind: ToolCallGroupKind;
  status: ToolStatus;
  children: ToolNode[];
}

export type ToolCallItem =
  | ExecuteToolCall
  | ReadToolCall
  | CreateFileToolCall
  | ModifyFileToolCall
  | DeleteFileToolCall
  | SearchToolCall
  | McpToolCall
  | WebFetchToolCall
  | SpawnSubagentToolCall
  | CreatePlanToolCall
  | UnknownToolCall;

export type ToolNode = ToolCallItem | ToolGroup;

const toolChildrenSchema: z.ZodType<ToolNode[]> = z.lazy(() => z.array(toolNodeSchema));

export const baseToolCallItemSchema = z.object({
  id: z.string(),
  /** Stable order within the owning sibling list, assigned once by the reducer. */
  seq: z.number().int(),
  /** Provider tool call id, stable across tool_call and tool_call_update notifications. */
  toolCallId: z.string(),
  title: z.string(),
  status: toolStatusSchema,
  /** Provider/plugin-generated short input description for compact display. */
  inputSummary: z.string().optional(),
  /** Provider-reported text result, capped by the reducer; previewed where a row has room. */
  outputText: z.string().optional(),
  /** Short failure reason when the provider reported the call as failed. */
  error: z.string().optional(),
  /** Latest provider progress line while the call runs (MCP progress, for example). */
  progress: z.string().optional(),
  /** Raw provider parent id used to rebuild the tree; not a render link. */
  parentToolCallId: z.string().optional(),
  /** Nested provider or reducer-derived tool nodes owned by this call. */
  children: toolChildrenSchema.optional(),
  /** Image output references resolved through the conversation attachment API. */
  attachments: z.array(attachmentRefSchema).optional(),
});

export const executeToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('execute-tool-call'),
  command: z.string().optional(),
  /** Text output reported by ACP tool_call_update content when no live terminal is attached. */
  outputText: z.string().optional(),
  /** Managed terminal id when this execute call is backed by terminal state. */
  terminalId: z.string().optional(),
});

export const readToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('read-tool-call'),
  path: z.string().optional(),
  resource: z.string().optional(),
});

export const fileToolCallBaseSchema = baseToolCallItemSchema.extend({
  path: z.string(),
});

export const createFileToolCallSchema = fileToolCallBaseSchema.extend({
  kind: z.literal('create-file-tool-call'),
  content: z.string(),
});

export const modifyFileToolCallSchema = fileToolCallBaseSchema.extend({
  kind: z.literal('modify-file-tool-call'),
  oldText: z.string(),
  newText: z.string(),
});

export const deleteFileToolCallSchema = fileToolCallBaseSchema.extend({
  kind: z.literal('delete-file-tool-call'),
});

export const searchToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('search-tool-call'),
  query: z.string(),
  /** Search domain supplied by provider normalization when known. */
  scope: z.enum(['web', 'workspace']).optional(),
  /** Provider-reported approximate match count when available. */
  matchCount: z.number().int().optional(),
});

export const mcpToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('mcp-tool-call'),
  /** MCP server name/id when the provider exposes it separately from the tool name. */
  server: z.string().optional(),
  tool: z.string(),
});

export const webFetchToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('web-fetch-tool-call'),
  url: z.string(),
  pageTitle: z.string().optional(),
});

export const spawnSubagentToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('spawn-subagent-tool-call'),
  name: z.string(),
  /** True for async/background agents that can outlive the turn that launched them. */
  background: z.boolean().optional(),
  /** Provider/runtime id for matching later background-agent status updates. */
  agentId: z.string().optional(),
});

export const createPlanToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('create-plan-tool-call'),
  /** Session-scoped plan id resolved against PlanState. */
  planId: z.string(),
  /** The plan as it stood when this turn last updated it; the live plan slice keeps moving. */
  entries: z.array(planEntryInputSchema).optional(),
});

export const unknownToolCallSchema = baseToolCallItemSchema.extend({
  kind: z.literal('unknown-tool-call'),
  toolKind: z.string().nullable(),
  name: z.string(),
});

export const toolCallItemSchema = z.discriminatedUnion('kind', [
  executeToolCallSchema,
  readToolCallSchema,
  createFileToolCallSchema,
  modifyFileToolCallSchema,
  deleteFileToolCallSchema,
  searchToolCallSchema,
  mcpToolCallSchema,
  webFetchToolCallSchema,
  spawnSubagentToolCallSchema,
  createPlanToolCallSchema,
  unknownToolCallSchema,
]);

export const toolGroupSchema = z.object({
  kind: z.literal('tool-group'),
  id: z.string(),
  /** Stable order within the owning sibling list, derived from the first child. */
  seq: z.number().int(),
  label: z.string(),
  groupKind: toolCallGroupKindSchema,
  status: toolStatusSchema,
  children: toolChildrenSchema,
});

export const toolNodeSchema: z.ZodType<ToolNode> = z.lazy(() =>
  z.discriminatedUnion('kind', [
    executeToolCallSchema,
    readToolCallSchema,
    createFileToolCallSchema,
    modifyFileToolCallSchema,
    deleteFileToolCallSchema,
    searchToolCallSchema,
    mcpToolCallSchema,
    webFetchToolCallSchema,
    spawnSubagentToolCallSchema,
    createPlanToolCallSchema,
    unknownToolCallSchema,
    toolGroupSchema,
  ])
);
