import { useEffect, useMemo } from "react";
import { AlertCircle, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { useAcp } from "@renderer/state/acp";
import { useAgents } from "@renderer/state/agents";
import { useComposer } from "@renderer/state/composer";
import { effortOption, fastOption, modeChoice, modelOption } from "@shared/acp/options";
import type { PromptBlock, SessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

import { AuthPrompt } from "./AuthPrompt";
import { Composer } from "./Composer";
import { EffortChip, ModeChip, ModelChip } from "./ComposerChips";
import { ContextMeter } from "./ContextMeter";
import { TranscriptScopeContext, type TranscriptScope } from "./links/PathLink";
import { PlanCard } from "./PlanCard";
import { SessionHeader } from "./SessionHeader";
import { Transcript } from "./Transcript";
import { isAuthError } from "./view";

/**
 * One thread, one agent (plan §3): the header, the transcript, the pinned
 * plan above the composer, the composer — whose row under the box ends in
 * the context ring.
 *
 * The session's live state comes from the acp store; a session picked from
 * the index with no snapshot yet is loaded here, which is the "connecting"
 * and the "resumed from history" states. A reconnect that fails is the
 * error state, with the agent's login surfaced when that is the cause.
 *
 * The full-pane spinner is now the *last* resort, not the first (README,
 * "Opening a session"). A session whose transcript main has a snapshot of
 * paints it immediately and says `Reconnecting…` in the composer's row while
 * the agent comes back; only a session with no snapshot at all — one created
 * before there were snapshots — still waits behind "Connecting to …".
 */
export function SessionView({ session }: { session: Session }) {
  const state = useAcp((store) => store.sessions[session.id] ?? null);
  const loading = useAcp((store) => store.loading[session.id] ?? false);
  const reconnecting = useAcp((store) => store.reconnecting[session.id] ?? false);
  const loadError = useAcp((store) => store.loadErrors[session.id] ?? null);
  const ensureLoaded = useAcp((store) => store.ensureLoaded);
  const load = useAcp((store) => store.load);
  const cancel = useAcp((store) => store.cancel);
  const setMode = useAcp((store) => store.setMode);
  const setConfigOption = useAcp((store) => store.setConfigOption);
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
  // A reconnect behind a painted transcript is not the composer's business:
  // a prompt sent now is queued against the load and goes out when it lands
  // (`ensureLive` in src/main/acp/sessions.ts), so the box stays live and the
  // row under it says what is happening instead.
  const composerStatus: "ready" | "submitted" | "streaming" = running
    ? "streaming"
    : (state?.status === "connecting" || loading) && !reconnecting
      ? "submitted"
      : "ready";

  const chips = useMemo(() => {
    if (!state) {
      return null;
    }
    const model = modelOption(state.configOptions);
    const effort = effortOption(state.configOptions);
    const mode = modeChoice(state);
    const fast = fastOption(state.configOptions);
    const setOption = (configId: string, value: string | boolean) => void setConfigOption(session.id, configId, value);
    // One chip, two calls: `session/set_mode` for an agent that sends
    // `modes`, its `mode` config option for one that sends that instead.
    const chooseMode = (modeId: string) => {
      if (!mode) {
        return;
      }
      if (mode.source === "modes") {
        void setMode(session.id, modeId);
      } else if (mode.configId) {
        setOption(mode.configId, modeId);
      }
    };
    // The row under the box, left to right: `+`, the mode; then on the right
    // the model, the effort and how full the window is. The agent and the
    // project are the title bar's and the sidebar's. The mode is the one
    // permission control — the app has none of its own over the top of it —
    // and it is set through whichever of the two calls this agent answers
    // to (`modeChoice`). Everything else the agent exposes is the agent's
    // business: the composer is four decisions, not a settings panel.
    return {
      leading: mode ? (
        <ModeChip currentModeId={mode.currentModeId} modes={mode.modes} onChange={chooseMode} />
      ) : null,
      trailing: (
        <>
          {model ? (
            <ModelChip
              agentId={session.agentId}
              fast={fast}
              onChange={(_agentId, value) => setOption(model.id, value)}
              onFastChange={setOption}
              providers={[
                {
                  agentId: session.agentId,
                  agentName: agent?.name ?? session.agentId,
                  icon: agent?.icon ?? null,
                  model,
                },
              ]}
            />
          ) : null}
          {effort ? <EffortChip effort={effort} onChange={setOption} /> : null}
          <ContextMeter
            lastTurnUsage={state.lastTurnUsage}
            rateLimits={state.rateLimits}
            sessionId={session.id}
            sessionUsage={state.sessionUsage}
            usage={state.contextUsage}
          />
        </>
      ),
    };
  }, [state, session.id, session.agentId, agent?.icon, agent?.name, setMode, setConfigOption]);

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
          {/* A reconnect that failed behind a painted transcript: the
              transcript is still worth reading, so the failure is a line
              above the composer rather than a screen in place of it. */}
          {state && loadError && !loading ? (
            isAuthError(loadError) ? (
              <AuthPrompt agent={agent} message={loadError} onRetry={() => void load(session.id)} />
            ) : (
              <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] leading-5" data-reconnect-failed role="status">
                <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                <span className="min-w-0 flex-1 whitespace-pre-wrap">{loadError}</span>
                <Button className="h-6 gap-1 px-2 text-[12px]" onClick={() => void load(session.id)} size="sm" variant="outline">
                  <RotateCcw className="size-3" />
                  Reconnect
                </Button>
              </div>
            )
          ) : null}
          {state?.plan && state.plan.length > 0 ? (
            <PlanCard entries={state.plan} running={running} startedAt={planTurn?.startedAt ?? null} />
          ) : null}
          <Composer
            autoFocus
            chips={
              <>
                {chips?.leading ?? null}
                {reconnecting ? <Reconnecting /> : null}
              </>
            }
            commands={state?.availableCommands ?? []}
            disabled={!state || state.status === "connecting" || state.status === "closed"}
            onStop={() => void cancel(session.id)}
            onSubmit={onSubmit}
            placeholder={running ? "Send another message — it goes next" : "Do anything"}
            sessionId={session.id}
            status={composerStatus}
            trailing={chips?.trailing ?? null}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * The agent is coming back behind a transcript that is already on screen.
 *
 * Deliberately small and in the composer's row, beside the mode chip: the
 * transcript is readable, the box takes a prompt, and the only thing missing
 * is an adapter — which is a line of text's worth of news, not a screen's.
 */
function Reconnecting() {
  return (
    <span
      className="flex shrink-0 items-center gap-1 px-1 text-[12px] text-muted-foreground"
      data-reconnecting
      role="status"
    >
      <Loader2 className="size-3 animate-spin" />
      Reconnecting…
    </span>
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
