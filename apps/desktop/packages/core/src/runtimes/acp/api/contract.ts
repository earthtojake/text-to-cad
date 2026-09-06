import {
  defineContract,
  procedure,
  downloadFile,
  fallible,
  liveLog,
  liveModel,
  liveState,
  uploadFile,
} from '@emdash/wire/rpc';
import { z } from 'zod';
import { terminalStateSchema } from '#runtimes/acp/api/models';
import { agentStateSchema } from '#runtimes/acp/api/models/agents';
import {
  attachmentMimeTypeSchema,
  attachmentRefSchema,
} from '#runtimes/acp/api/models/attachments';
import {
  sessionConfigStateSchema,
  modelOptionSchema,
  sessionMcpServerSchema,
  sessionUsageSchema,
} from '#runtimes/acp/api/models/config';
import { planStateSchema } from '#runtimes/acp/api/models/plan';
import { promptDraftSchema } from '#runtimes/acp/api/models/prompt';
import { sessionStateSchema, sessionSummarySchema } from '#runtimes/acp/api/models/session';
import { transcriptTurnSchema } from '#runtimes/acp/api/models/turns';
import {
  acpAttachmentErrorSchema,
  acpCancelTurnErrorSchema,
  acpChangeQueuePromptOrderErrorSchema,
  acpDeleteQueuedPromptErrorSchema,
  acpEditQueuedPromptErrorSchema,
  acpExportRawLogErrorSchema,
  acpExportTranscriptErrorSchema,
  acpGetHistoryErrorSchema,
  acpKillErrorSchema,
  acpResolvePermissionErrorSchema,
  acpResumeErrorSchema,
  acpSendPromptErrorSchema,
  acpSetModeOptionErrorSchema,
  acpSetModelOptionErrorSchema,
  acpSetPromptDraftErrorSchema,
  acpStartErrorSchema,
} from './errors';
import {
  acpResumeInputSchema,
  acpStartInputSchema,
  cancelTurnCommandSchema,
  changeQueuePromptOrderCommandSchema,
  deleteAttachmentCommandSchema,
  deleteAttachmentsCommandSchema,
  deleteQueuedPromptCommandSchema,
  downloadAttachmentCommandSchema,
  editQueuedPromptCommandSchema,
  exportAcpTranscriptCommandSchema,
  exportRawAcpLogCommandSchema,
  historyPageInputSchema,
  historyPageSchema,
  killCommandSchema,
  resolvePermissionCommandSchema,
  resumeResultSchema,
  sendPromptCommandSchema,
  sendPromptResponseSchema,
  setModeOptionCommandSchema,
  setModelOptionCommandSchema,
  setPromptDraftCommandSchema,
  uploadAttachmentCommandSchema,
  uploadAttachmentResponseSchema,
} from './schemas';

const startResultSchema = z.object({ sessionId: z.string() });
const sessionKeySchema = z.object({ conversationId: z.string() });
const terminalOutputKeySchema = z.object({ terminalId: z.string() });

export const acpApiContract = defineContract({
  discoverModels: procedure({
    input: z.object({ providerId: z.string(), env: z.record(z.string(), z.string()).optional() }),
    output: z.array(modelOptionSchema),
  }),
  start: fallible({
    input: acpStartInputSchema,
    data: startResultSchema,
    error: acpStartErrorSchema,
  }),
  resume: fallible({
    input: acpResumeInputSchema,
    data: resumeResultSchema,
    error: acpResumeErrorSchema,
  }),
  /**
   * Terminates any active process and removes the persisted active intent — the session no
   * longer auto-resumes across daemon restarts. The conversation record stays resumable
   * manually.
   */
  kill: fallible({
    input: killCommandSchema,
    error: acpKillErrorSchema,
  }),
  sendPrompt: fallible({
    input: sendPromptCommandSchema,
    data: sendPromptResponseSchema,
    error: acpSendPromptErrorSchema,
  }),
  editQueuedPrompt: fallible({
    input: editQueuedPromptCommandSchema,
    error: acpEditQueuedPromptErrorSchema,
  }),
  deleteQueuedPrompt: fallible({
    input: deleteQueuedPromptCommandSchema,
    error: acpDeleteQueuedPromptErrorSchema,
  }),
  changeQueuePromptOrder: fallible({
    input: changeQueuePromptOrderCommandSchema,
    error: acpChangeQueuePromptOrderErrorSchema,
  }),
  cancelTurn: fallible({
    input: cancelTurnCommandSchema,
    error: acpCancelTurnErrorSchema,
  }),
  setModelOption: fallible({
    input: setModelOptionCommandSchema,
    error: acpSetModelOptionErrorSchema,
  }),
  setModeOption: fallible({
    input: setModeOptionCommandSchema,
    error: acpSetModeOptionErrorSchema,
  }),
  resolvePermission: fallible({
    input: resolvePermissionCommandSchema,
    error: acpResolvePermissionErrorSchema,
  }),
  setPromptDraft: fallible({
    input: setPromptDraftCommandSchema,
    error: acpSetPromptDraftErrorSchema,
  }),
  exportAcpTranscript: fallible({
    input: exportAcpTranscriptCommandSchema,
    data: z.object({ transcript: z.string() }),
    error: acpExportTranscriptErrorSchema,
  }),
  exportRawAcpLog: fallible({
    input: exportRawAcpLogCommandSchema,
    data: z.object({ log: z.string() }),
    error: acpExportRawLogErrorSchema,
  }),
  uploadAttachment: uploadFile({
    input: uploadAttachmentCommandSchema,
    accept: attachmentMimeTypeSchema.options,
    result: uploadAttachmentResponseSchema,
    error: acpAttachmentErrorSchema,
  }),
  downloadAttachment: downloadFile({
    input: downloadAttachmentCommandSchema,
    meta: attachmentRefSchema,
    error: acpAttachmentErrorSchema,
  }),
  deleteAttachment: fallible({
    input: deleteAttachmentCommandSchema,
    error: acpAttachmentErrorSchema,
  }),
  /**
   * Maintenance verb for conversation deletion (spec §3.6, §4.2): removes every attachment
   * stored for the conversation. Invoked by the conversation removal verb alongside
   * `kill`; idempotent for absent conversations.
   */
  deleteAttachments: fallible({
    input: deleteAttachmentsCommandSchema,
    error: acpAttachmentErrorSchema,
  }),
  getHistory: fallible({
    input: historyPageInputSchema,
    data: historyPageSchema,
    error: acpGetHistoryErrorSchema,
  }),
  sessions: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: z.record(z.string(), sessionSummarySchema) }),
    },
  }),
  session: liveModel({
    key: sessionKeySchema,
    states: {
      state: liveState({ data: sessionStateSchema }),
      config: liveState({ data: sessionConfigStateSchema }),
      usage: liveState({ data: sessionUsageSchema.nullable() }),
      plan: liveState({ data: planStateSchema.nullable() }),
      agents: liveState({ data: z.array(agentStateSchema) }),
      activeTurn: liveState({ data: transcriptTurnSchema.nullable() }),
      draft: liveState({ data: promptDraftSchema.nullable() }),
      terminals: liveState({ data: z.array(terminalStateSchema) }),
      mcpServers: liveState({ data: z.array(sessionMcpServerSchema) }),
    },
  }),
  terminalOutput: liveLog({ key: terminalOutputKeySchema }),
});

export type AcpApiContract = typeof acpApiContract;
