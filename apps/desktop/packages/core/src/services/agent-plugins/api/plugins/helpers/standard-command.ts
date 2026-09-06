import { formatCommandLine, quoteArg } from '#primitives/exec/api';
import type {
  AgentCommand,
  CommandContext,
} from '#services/agent-plugins/api/plugins/capabilities/prompt';

/** Wrap a command with stdin pipe delivery for an initial prompt. */
export function wrapWithStdinPipe(cmd: AgentCommand, prompt: string): AgentCommand {
  const agentLine = formatCommandLine(cmd, 'posix');
  const shellLine = `printf '%s\n' ${quoteArg(prompt, 'posix')} | ${agentLine}`;
  return { command: 'bash', args: ['-c', shellLine], env: cmd.env };
}

/**
 * Spec for standard command building; mirrors `AgentProviderDefinition` fields
 * but typed for use in buildStandardCommand.
 */
export type StandardCommandSpec = {
  /** Args always appended after the binary. */
  defaultArgs?: string[];
  /** Flag for auto-approve mode, e.g. '--dangerously-skip-permissions'. */
  autoApproveFlag?: string;
  /**
   * Flag for initial prompt, e.g. '-i' or '--prompt'. Empty string = positional
   * (prompt appended as last arg without a flag). Leave undefined to skip prompt injection.
   */
  initialPromptFlag?: string;
  /** Whether the initial prompt should be delivered via stdin pipe instead of CLI args. */
  initialPromptViaStdinPipe?: boolean;
  /**
   * Flag for session resume, e.g. '--resume'. When isResuming and sessionId is set,
   * the session ID is appended after this flag. When sessionIdOnResumeOnly is true and
   * we are resuming without a sessionId, `resumeWithoutSessionFlag` is used.
   */
  resumeFlag?: string;
  /**
   * Flag for passing a session ID, e.g. '--session-id'. On fresh sessions (non-resuming),
   * the emdash session UUID is passed. On resume sessions, `resumeFlag` is used instead.
   * If both are the same flag (e.g. grok/copilot), set sessionIdOnResumeOnly=true.
   */
  sessionIdFlag?: string;
  /** Only pass sessionId when resuming, not on fresh sessions. */
  sessionIdOnResumeOnly?: boolean;
  /** Resume flag used when sessionIdOnResumeOnly=true but sessionId is absent (no stored session yet). */
  resumeWithoutSessionFlag?: string;
  /** A flag appended when starting a fresh conversation (e.g. letta's --new). */
  newConversationFlag?: string;
  /**
   * When true, sessionIdFlag is injected on both fresh AND resume sessions.
   * Use for providers like Antigravity that identify conversations by ID on every invocation.
   */
  sessionIdAlways?: boolean;
  /** When true, skip auto-approve flag on resume (kimi special case). */
  omitAutoApproveOnResume?: boolean;
  /** List of singleton flags to deduplicate (keep first occurrence only). */
  deduplicateFlags?: string[];
  /** Validate a session ID before using it for resume (e.g. opencode needs 'ses' prefix). */
  validateSessionId?: (id: string) => boolean;
  /** Extra static env vars to inject (on top of ctx env). */
  extraEnv?: Record<string, string>;
  /**
   * CLI flag for model selection, e.g. '--model' or '-m'.
   * When ctx.model is non-empty, appendFlagValue(args, modelFlag, ctx.model) is called.
   * Supports both '--flag value' and '--flag=value' forms via appendFlagValue.
   */
  modelFlag?: string;
};

/**
 * Build a standard AgentCommand from a CommandContext, applying the spec's flag patterns.
 * Handles: defaultArgs, resume/session flags, auto-approve, and prompt delivery.
 */
export function buildStandardCommand(ctx: CommandContext, spec: StandardCommandSpec): AgentCommand {
  const args: string[] = [];
  const env: Record<string, string> = { ...spec.extraEnv };

  // Default args (e.g. goose's ['run', '-s'])
  if (spec.defaultArgs?.length) {
    args.push(...spec.defaultArgs);
  }

  // Session / resume logic.
  // For sessionIdOnResumeOnly providers, use only the provider-native session id.
  // If providerSessionId is absent, validSessionId will be undefined → fallback flags apply.
  // For all other providers, the emdash session UUID (sessionId) is used.
  const rawSessionId = spec.sessionIdOnResumeOnly ? ctx.providerSessionId : ctx.sessionId;
  const hasSessionId = !!rawSessionId;
  const validSessionId =
    hasSessionId && spec.validateSessionId
      ? spec.validateSessionId(rawSessionId!)
        ? rawSessionId!
        : undefined
      : rawSessionId;

  if (ctx.isResuming) {
    if (spec.sessionIdAlways && spec.sessionIdFlag && ctx.sessionId) {
      // Always inject session ID on resume too (e.g. Antigravity --conversation=)
      appendFlagValue(args, spec.sessionIdFlag, ctx.sessionId);
    } else if (spec.resumeFlag) {
      if (spec.sessionIdFlag && validSessionId) {
        // resumeFlag takes the session ID (e.g. '--resume <id>' or '-r <id>')
        args.push(...splitFlag(spec.resumeFlag), validSessionId);
      } else if (spec.sessionIdFlag && !spec.sessionIdOnResumeOnly) {
        // Use emdash UUID
        args.push(...splitFlag(spec.resumeFlag), ctx.sessionId!);
      } else if (spec.resumeWithoutSessionFlag) {
        args.push(...splitFlag(spec.resumeWithoutSessionFlag));
      } else {
        args.push(...splitFlag(spec.resumeFlag));
      }
    }
  } else {
    // Fresh session
    if (spec.sessionIdFlag && !spec.sessionIdOnResumeOnly && ctx.sessionId) {
      appendFlagValue(args, spec.sessionIdFlag, ctx.sessionId);
    } else if (spec.newConversationFlag) {
      args.push(spec.newConversationFlag);
    }
  }

  // Auto-approve
  const skipAutoApprove = spec.omitAutoApproveOnResume && ctx.isResuming;
  if (ctx.autoApprove && spec.autoApproveFlag && !skipAutoApprove) {
    args.push(...splitFlag(spec.autoApproveFlag));
  }

  // Model selection
  if (spec.modelFlag && ctx.model) {
    appendFlagValue(args, spec.modelFlag, ctx.model);
  }

  // User extra args
  if (ctx.extraArgs?.length) {
    args.push(...ctx.extraArgs);
  }

  // Initial prompt — only on fresh sessions
  if (!ctx.isResuming && ctx.initialPrompt) {
    if (spec.initialPromptViaStdinPipe) {
      // Handled later by caller via wrapWithStdinPipe
    } else if (spec.initialPromptFlag !== undefined) {
      if (spec.initialPromptFlag === '') {
        args.push(ctx.initialPrompt);
      } else {
        args.push(...splitFlag(spec.initialPromptFlag), ctx.initialPrompt);
      }
    }
  }

  const finalArgs = spec.deduplicateFlags?.length ? dedupeFlags(args, spec.deduplicateFlags) : args;

  const command: AgentCommand = { command: ctx.cli, args: finalArgs, env };

  // Wrap with stdin pipe if needed
  if (!ctx.isResuming && ctx.initialPrompt && spec.initialPromptViaStdinPipe) {
    return wrapWithStdinPipe(command, ctx.initialPrompt);
  }

  return command;
}

function splitFlag(flag: string): string[] {
  return flag.split(/\s+/).filter(Boolean);
}

function appendFlagValue(args: string[], flag: string, value: string): void {
  if (flag.endsWith('=')) {
    args.push(`${flag}${value}`);
  } else {
    args.push(...splitFlag(flag), value);
  }
}

function dedupeFlags(args: string[], flags: string[]): string[] {
  const singletons = new Set(flags);
  const seen = new Set<string>();
  return args.filter((arg) => {
    if (!singletons.has(arg)) return true;
    if (seen.has(arg)) return false;
    seen.add(arg);
    return true;
  });
}
