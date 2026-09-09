import type { Result } from '@emdash/shared';
import type {
  TuiAgentStartInput,
  TuiInputError,
  TuiResumeOutcome,
  TuiResumeError,
  TuiSessionControlError,
  TuiStartOutcome,
  TuiStartError,
} from '#runtimes/tui-agents/api';
import type { TuiAgentsRuntime } from '#runtimes/tui-agents/node/runtime/runtime';

export type StartTuiSessionInput = TuiAgentStartInput;

export function createTuiAgentsProcedures(runtime: TuiAgentsRuntime) {
  return {
    start(
      input: StartTuiSessionInput
    ): Promise<Result<{ outcome: TuiStartOutcome }, TuiStartError>> {
      return runtime.startSession(input);
    },
    resume(
      input: StartTuiSessionInput
    ): Promise<Result<{ outcome: TuiResumeOutcome }, TuiResumeError>> {
      return runtime.resumeSession(input);
    },
    stop(input: { conversationId: string }): Result<void, TuiSessionControlError> {
      return runtime.stopSession(input.conversationId);
    },
    delete(input: { conversationId: string }): Promise<Result<void, TuiSessionControlError>> {
      return runtime.deleteSession(input.conversationId);
    },
    kill(input: { conversationId: string }): Promise<Result<void, TuiSessionControlError>> {
      return runtime.killSession(input.conversationId);
    },
    sendInput(input: { conversationId: string; data: string }): Result<void, TuiInputError> {
      return runtime.sendInput(input.conversationId, input.data);
    },
    resize(input: {
      conversationId: string;
      cols: number;
      rows: number;
    }): Result<void, TuiInputError> {
      return runtime.resize(input.conversationId, input.cols, input.rows);
    },
  };
}

export type TuiAgentsProcedures = ReturnType<typeof createTuiAgentsProcedures>;
