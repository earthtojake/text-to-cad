import { useEffect, useMemo } from "react";
import { AlertCircle, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { useAcp } from "@renderer/state/acp";
import { useAgents } from "@renderer/state/agents";
import { useComposer } from "@renderer/state/composer";
import type { PromptBlock, SessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

import { AuthPrompt } from "./AuthPrompt";
import { Composer } from "./Composer";
import { ApprovalChip, EffortChip, ModeChip, ModelChip, OptionsChip } from "./ComposerChips";
import { FilesChangedPill } from "./FilesChangedPill";
import { TranscriptScopeContext, type TranscriptScope } from "./links/PathLink";
import { PlanCard } from "./PlanCard";
import { SessionHeader } from "./SessionHeader";
import { Transcript } from "./Transcript";
import { isAuthError, isEffortOption } from "./view";

/**
 * One thread, one agent (plan §3): the header, the transcript, the pinned
 * plan and the files-changed pill above the composer, the composer.
 *
 * The session's live state comes from the acp store; a session picked from
 * the index with no snapshot yet is loaded here, which is the "connecting"
 * and the "resumed from history" states. A reconnect that fails is the
 * error state, with the agent's login surfaced when that is the cause.
 */
export function SessionView({ session }: { session: Session }) {
  const state = useAcp((store) => store.sessions[session.id] ?? null);
  const loading = useAcp((store) => store.loading[session.id] ?? false);
  const loadError = useAcp((store) => store.loadErrors[session.id] ?? null);
  const ensureLoaded = useAcp((store) => store.ensureLoaded);
  const load = useAcp((store) => store.load);
  const cancel = useAcp((store) => store.cancel);
  const setMode = useAcp((store) => store.setMode);
  const setConfigOption = useAcp((store) => store.setConfigOption);
  const setApprovalMode = useAcp((store) => store.setApprovalMode);
  const submit = useComposer((store) => store.submit);
  const agents = useAgents((store) => store.agents);
  const agent = agents.find((candidate) => candidate.id === session.agentId) ?? null;

  useEffect(() => {
    void ensureLoaded(session.id);
  }, [session.id, ensureLoaded]);

  const onSubmit = (text: string, content: PromptBlock[]) => submit(session.id, text, content);

  // What a path in this thread's prose is relative to: its worktree when it
  // runs in one (plan §9), else the project. `links/PathLink` reads it.
  const scope = useMemo<TranscriptScope>(
    () => ({ projectId: session.projectId, root: session.worktreePath ?? null }),
    [session.projectId, session.worktreePath],
  );

  const retry = () => {
    const lastPrompt = lastUserPrompt(state);
    if (lastPrompt) {
      void submit(session.id, promptText(lastPrompt), lastPrompt);
    }
  };

  const running = state?.status === "running" || state?.status === "waiting";
  const composerStatus: "ready" | "submitted" | "streaming" = running
    ? "streaming"
    : state?.status === "connecting" || loading
      ? "submitted"
      : "ready";

  const chips = useMemo(() => {
    if (!state) {
      return null;
    }
    const selects = state.configOptions.filter((option) => option.type === "select");
    const booleans = state.configOptions.filter((option) => option.type === "boolean");
    const model = selects.find((option) => option.category === "model") ?? null;
    const effort = selects.find(isEffortOption) ?? null;
    const preset = selects.find((option) => option.category === "mode") ?? null;
    const others = selects.filter((option) => option !== model && option !== effort && option !== preset);
    const setOption = (configId: string, value: string | boolean) => void setConfigOption(session.id, configId, value);
    // Codex's row, left to right: `+`, approval; then on the right the model,
    // the effort beside it, the options glyph, mic, send. The agent and the
    // project are the title bar's and the sidebar's, not the composer's. An
    // agent with modes but no `mode` config option (Claude) gets its modes as
    // a chip of their own, beside approval.
    return {
      leading: (
        <>
          <ApprovalChip
            mode={state.approvalMode}
            onChange={(mode) => void setApprovalMode(session.id, mode)}
            onPresetChange={setOption}
            preset={preset}
          />
          {state.modes.length > 1 && !preset ? (
            <ModeChip
              currentModeId={state.currentModeId}
              modes={state.modes}
              onChange={(modeId) => void setMode(session.id, modeId)}
            />
          ) : null}
        </>
      ),
      trailing: (
        <>
          {model ? <ModelChip icon={agent?.icon} model={model} onChange={setOption} /> : null}
          {effort ? <EffortChip effort={effort} onChange={setOption} /> : null}
          <OptionsChip booleans={booleans} onSelect={setOption} onToggle={setOption} selects={others} />
        </>
      ),
    };
  }, [state, session.id, agent?.icon, setApprovalMode, setMode, setConfigOption]);

  const planTurn =
    state?.turns.findLast((turn) => turn.role === "agent" && turn.parts.some((part) => part.type === "plan")) ?? null;
  // A failed prompt is already in the transcript with its Retry; the banner
  // is for a connection that died with nothing to attach the message to.
  const lastAgentTurn = state?.turns.findLast((turn) => turn.role === "agent") ?? null;
  const errorInTranscript = lastAgentTurn?.parts.at(-1)?.type === "error";
  const showErrorBanner = state?.status === "error" && !!state.error && !errorInTranscript;

  return (
    <div className="flex h-full min-h-0 flex-col" data-session-view={session.id} data-session-status={state?.status ?? (loading ? "loading" : "detached")}>
      <SessionHeader session={session} title={session.title} />

      {state ? (
        <TranscriptScopeContext.Provider value={scope}>
          <Transcript onReconnect={() => void load(session.id)} onRetry={retry} state={state} />
        </TranscriptScopeContext.Provider>
      ) : loadError ? (
        isAuthError(loadError) || agent?.auth === "unauthenticated" ? (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <AuthPrompt agent={agent} message={loadError} onRetry={() => void load(session.id)} />
          </div>
        ) : (
          <LoadFailed message={loadError} onRetry={() => void load(session.id)} />
        )
      ) : (
        <Connecting agentName={agent?.name ?? session.agentId} />
      )}

      <div className="shrink-0 px-6 pb-4">
        <div className="mx-auto flex w-full max-w-[720px] flex-col gap-2">
          {showErrorBanner && state?.error && !isAuthError(state.error) ? (
            <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] leading-5" role="status">
              <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
              <span className="min-w-0 flex-1 whitespace-pre-wrap">{state.error}</span>
              <Button className="h-6 gap-1 px-2 text-[12px]" onClick={() => void load(session.id)} size="sm" variant="outline">
                <RotateCcw className="size-3" />
                Reconnect
              </Button>
            </div>
          ) : null}
          {showErrorBanner && state?.error && isAuthError(state.error) ? (
            <AuthPrompt agent={agent} message={state.error} onRetry={() => void load(session.id)} />
          ) : null}
          {state?.plan && state.plan.length > 0 ? (
            <PlanCard entries={state.plan} running={running} startedAt={planTurn?.startedAt ?? null} />
          ) : null}
          <FilesChangedPill deletions={session.deletions} files={session.changedFiles} insertions={session.insertions} />
          <Composer
            autoFocus
            chips={chips?.leading ?? null}
            commands={state?.availableCommands ?? []}
            disabled={!state || state.status === "connecting" || state.status === "closed"}
            onStop={() => void cancel(session.id)}
            onSubmit={onSubmit}
            placeholder={running ? "Send another message — it goes next" : "Do anything"}
            sessionId={session.id}
            status={composerStatus}
            trailing={chips?.trailing ?? null}
          />
          {state?.contextUsage ? <ContextFooter used={state.contextUsage.used} size={state.contextUsage.size} cost={state.contextUsage.cost} /> : null}
        </div>
      </div>
    </div>
  );
}

function Connecting({ agentName }: { agentName: string }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 text-center" data-connecting>
      <Loader2 className="size-4 animate-spin text-muted-foreground" />
      <p className="text-[13px] text-muted-foreground">Connecting to {agentName}…</p>
    </div>
  );
}

function LoadFailed({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 px-6 text-center" data-load-failed>
      <AlertCircle className="size-4 text-destructive" />
      <p className="max-w-[480px] text-[13px] leading-5 whitespace-pre-wrap text-muted-foreground">{message}</p>
      <Button className="h-7 gap-1.5 text-[12px]" onClick={onRetry} size="sm" variant="outline">
        <RotateCcw className="size-3.5" />
        Reconnect
      </Button>
    </div>
  );
}

/** A small footer under the composer: how full the context window is, and what it has cost. */
function ContextFooter({
  used,
  size,
  cost,
}: {
  used: number;
  size: number;
  cost: { amount: number; currency: string } | null;
}) {
  const percent = size > 0 ? Math.min(100, Math.round((used / size) * 100)) : 0;
  return (
    <div className="flex items-center justify-end gap-2 px-2 font-mono text-[10px] text-muted-foreground tabular-nums" data-context-footer>
      <span title={`${used} of ${size} tokens`}>{percent}% context</span>
      {cost ? <span>· {formatCostShort(cost.amount, cost.currency)}</span> : null}
    </div>
  );
}

function formatCostShort(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: amount < 1 ? 3 : 2 }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function lastUserPrompt(state: SessionState | null): PromptBlock[] | null {
  const turn = state?.turns.findLast((candidate) => candidate.role === "user");
  if (!turn) {
    return null;
  }
  const blocks: PromptBlock[] = [];
  for (const part of turn.parts) {
    if (part.type === "text") {
      blocks.push({ type: "text", text: part.text });
    } else if (part.type === "image") {
      blocks.push({ type: "image", data: part.data, mimeType: part.mimeType, uri: null });
    } else if (part.type === "resource_link") {
      blocks.push({ type: "resource_link", uri: part.uri, name: part.name, mimeType: null, title: null });
    }
  }
  return blocks.length > 0 ? blocks : null;
}

function promptText(blocks: PromptBlock[]): string {
  return blocks
    .filter((block): block is Extract<PromptBlock, { type: "text" }> => block.type === "text")
    .map((block) => block.text)
    .join("\n");
}
