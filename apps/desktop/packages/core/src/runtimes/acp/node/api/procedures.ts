import { ok, type Result } from '@emdash/shared';
import { blobSourceFromBytes, type WireFile } from '@emdash/wire/rpc';
import type {
  AcpAttachmentError,
  AcpCancelTurnError,
  AcpChangeQueuePromptOrderError,
  AcpDeleteQueuedPromptError,
  AcpEditQueuedPromptError,
  AcpExportRawLogError,
  AcpExportTranscriptError,
  AcpGetHistoryError,
  AcpKillError,
  AcpResolvePermissionError,
  AcpResumeError,
  AcpSendPromptError,
  AcpSetModeOptionError,
  AcpSetModelOptionError,
  AcpSetPromptDraftError,
  AcpStartError,
  AcpStartInputWire,
  AttachmentMimeType,
  AttachmentRef,
  HistoryPage,
  PromptDraftUpdate,
  PromptInput,
  PromptPlacement,
  ResumeResult,
} from '#runtimes/acp/api';
import type { AcpRuntime } from '#runtimes/acp/node/runtime/runtime';

export type StartSessionInput = AcpStartInputWire;

export function createAcpProcedures(runtime: AcpRuntime) {
  return {
    discoverModels(input: { providerId: string; env?: Record<string, string> }) {
      return runtime.discoverModels(input);
    },
    start(input: StartSessionInput): Promise<Result<{ sessionId: string }, AcpStartError>> {
      return runtime.startSession(input);
    },
    resume(
      input: StartSessionInput & { sessionId: string }
    ): Promise<Result<ResumeResult, AcpResumeError>> {
      return runtime.resumeSession(input);
    },
    kill(input: { conversationId: string }): Promise<Result<void, AcpKillError>> {
      return runtime.killSession(input.conversationId);
    },
    sendPrompt(input: {
      conversationId: string;
      prompt: PromptInput;
      placement?: PromptPlacement;
    }): Promise<Result<{ queued: boolean }, AcpSendPromptError>> {
      return runtime.sendPrompt(input.conversationId, input.prompt, input.placement);
    },
    editQueuedPrompt(input: {
      conversationId: string;
      id: string;
      input: PromptInput;
    }): Result<void, AcpEditQueuedPromptError> {
      return runtime.editQueuedPrompt(input.conversationId, input.id, input.input);
    },
    deleteQueuedPrompt(input: {
      conversationId: string;
      id: string;
    }): Result<void, AcpDeleteQueuedPromptError> {
      return runtime.deleteQueuedPrompt(input.conversationId, input.id);
    },
    changeQueuePromptOrder(input: {
      conversationId: string;
      ids: string[];
    }): Result<void, AcpChangeQueuePromptOrderError> {
      return runtime.changeQueuePromptOrder(input.conversationId, input.ids);
    },
    cancelTurn(input: { conversationId: string }): Promise<Result<void, AcpCancelTurnError>> {
      return runtime.cancelTurn(input.conversationId);
    },
    setPromptDraft(input: {
      conversationId: string;
      draft: PromptDraftUpdate;
    }): Result<void, AcpSetPromptDraftError> {
      return runtime.setPromptDraft(input.conversationId, input.draft);
    },
    setModelOption(input: {
      conversationId: string;
      dimension: 'model' | 'effort';
      value: string;
    }): Promise<Result<void, AcpSetModelOptionError>> {
      return runtime.setModelOption(input.conversationId, input.dimension, input.value);
    },
    setModeOption(input: {
      conversationId: string;
      value: string;
    }): Promise<Result<void, AcpSetModeOptionError>> {
      return runtime.setModeOption(input.conversationId, input.value);
    },
    resolvePermission(input: {
      conversationId: string;
      requestId: string;
      optionId: string;
    }): Result<void, AcpResolvePermissionError> {
      return runtime.resolvePermission(input.conversationId, input.requestId, input.optionId);
    },
    exportAcpTranscript(input: {
      conversationId: string;
    }): Result<{ transcript: string }, AcpExportTranscriptError> {
      const result = runtime.exportParsedTranscript(input.conversationId);
      return result.success ? ok({ transcript: result.data }) : result;
    },
    exportRawAcpLog(input: {
      conversationId: string;
    }): Result<{ log: string }, AcpExportRawLogError> {
      const result = runtime.exportRawAcpLog(input.conversationId);
      return result.success ? ok({ log: result.data }) : result;
    },
    async uploadAttachment(
      input: {
        conversationId: string;
        originalPath?: string;
      },
      file: WireFile
    ): Promise<Result<AttachmentRef, AcpAttachmentError>> {
      const data = input.originalPath ? undefined : await file.bytes();
      return runtime.uploadAttachment({
        conversationId: input.conversationId,
        data,
        mimeType: file.mimeType as AttachmentMimeType,
        name: file.name,
        originalPath: input.originalPath,
      });
    },
    async downloadAttachment(input: {
      conversationId: string;
      attachmentId: string;
    }): Promise<
      Result<{ meta: AttachmentRef; source: AsyncIterable<Uint8Array> }, AcpAttachmentError>
    > {
      const result = await runtime.downloadAttachment(input.conversationId, input.attachmentId);
      if (!result.success) return result;
      return ok({
        meta: result.data.ref,
        source: blobSourceFromBytes(result.data.data),
      });
    },
    deleteAttachment(input: {
      conversationId: string;
      attachmentId: string;
    }): Promise<Result<void, AcpAttachmentError>> {
      return runtime.deleteAttachment(input.conversationId, input.attachmentId);
    },
    deleteAttachments(input: {
      conversationId: string;
    }): Promise<Result<void, AcpAttachmentError>> {
      return runtime.deleteConversationAttachments(input.conversationId);
    },
    getHistory(input: {
      conversationId: string;
      before?: number;
      limit: number;
    }): Result<HistoryPage, AcpGetHistoryError> {
      return runtime.getHistory(input.conversationId, input.before, input.limit);
    },
  };
}

export type AcpProcedures = ReturnType<typeof createAcpProcedures>;
