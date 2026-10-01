import { useEffect, useRef, useState } from "react";
import { Check, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { AgentMark } from "@renderer/features/settings/AgentMark";
import { JobLog, useJob } from "@renderer/features/settings/AgentDrawer";
import { cn } from "@renderer/lib/utils";
import { useAgents } from "@renderer/state/agents";
import { ONBOARDING_AGENT_IDS } from "@renderer/state/onboarding";
import { useUi } from "@renderer/state/ui";
import type { AgentStatus } from "@shared/agents";

/*
 * Getting an agent running: what the new-session screen shows when no agent
 * is ready, what a session shows when its agent's CLI is gone, and the
 * rows the welcome's agent step lists.
 */

/**
 * Main's refusal to spawn an agent whose CLI is not on this machine
 * (`ensureLive`/`probeOptions` in src/main/acp/sessions.ts:
 * `${provider.name} is not installed`). It crosses IPC as a plain message —
 * there is no typed reason — so this is the one place that reads it.
 */
export function isNotInstalledError(message: string | null | undefined): boolean {
  return /\bis not installed\.?$/.test((message ?? "").trim());
}

/**
 * A session can start with it: it can launch — its CLI is installed, or its
 * adapter runs without one (`launchWithoutBinary`: Claude Code, Codex) — and
 * detection found it signed in, or it needs no sign-in.
 *
 * Deliberately cautious: "unknown" (detection had no env var, check command
 * or credentials file to go by — Copilot and Kiro always, Claude Code in the
 * keychain) is not ready here. Onboarding uses this, so its Continue says
 * "without an agent" until one is confirmed. The new-session screen's "No
 * agent ready" card is deliberately permissive instead: it counts only
 * "unauthenticated" against an agent, because an unknown one may well work
 * and nagging on every new session would be wrong (NewSession.tsx).
 */
export function isAgentReady(agent: AgentStatus): boolean {
  return (agent.installed || agent.launchWithoutBinary) && (agent.auth === "authenticated" || agent.auth === "not-required");
}

/**
 * Not ready, but one sign-in from it: the CLI is here to run its login
 * (`loginCommand` in src/main/agents/auth.ts runs the binary, so an
 * adapter-only agent has to be installed before it can sign in).
 */
export function canSignIn(agent: AgentStatus): boolean {
  return agent.installed && !isAgentReady(agent);
}

/**
 * One agent with the step that gets it running — Install, then Sign in —
 * and the job's output under it. The welcome's agent step, the new-session
 * screen's "no agent ready" card and a session whose CLI is gone.
 */
export function AgentRow({ agent }: { agent: AgentStatus }) {
  const install = useAgents((state) => state.install);
  const login = useAgents((state) => state.login);
  const refresh = useAgents((state) => state.refresh);
  // The step the row is at: a job of that kind still running for this agent is the row's own,
  // whoever started it (the row may be a remount of the one that did).
  const { jobId, output, running, failure, start } = useJob(agent.id, agent.installed ? "login" : "install", agent.installed && agent.auth === "authenticated");

  // An install or sign-in changes what detection would find: look again once it ends.
  useEffect(() => {
    if (jobId && !running) {
      void refresh();
    }
  }, [jobId, running, refresh]);

  const ready = isAgentReady(agent);
  // The drawer's words (Settings › Agents): "Not signed in" only when
  // detection found the agent signed out; "unknown" claims nothing.
  // A cached "not installed" from the last launch is provisional too: no Install until it is confirmed.
  const checkingInstall = agent.probing === true && !agent.installed && !ready;
  const status = ready ? "Ready" : checkingInstall ? "Checking…" : !agent.installed ? "Not installed" : agent.auth === "unauthenticated" ? (agent.probing ? "Checking…" : "Not signed in") : "Installed";

  return (
    <div className="rounded-lg border px-3 py-2.5" data-onboarding-agent={agent.id}>
      <div className="flex items-center gap-3">
        <AgentMark icon={agent.icon} id={agent.id} name={agent.name} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{agent.name}</p>
          <p className={cn("text-xs", ready ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground")}>
            {status}
          </p>
        </div>
        {ready ? (
          <Check aria-label="Ready" className="size-4 text-emerald-500" />
        ) : checkingInstall ? (
          <Loader2 aria-label="Checking" className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none" />
        ) : !agent.installed ? (
          <Button className="h-7 gap-1.5" disabled={running} onClick={() => void start(() => install(agent.id))} size="sm">
            {running ? <Loader2 className="size-3.5 animate-spin" /> : null}
            Install
          </Button>
        ) : (
          <Button className="h-7 gap-1.5" disabled={running} onClick={() => void start(() => login(agent.id))} size="sm">
            {running ? <Loader2 className="size-3.5 animate-spin" /> : null}
            Sign in
          </Button>
        )}
      </div>
      {jobId || failure ? <JobLog failure={failure} log={jobId !== null} output={output} /> : null}
    </div>
  );
}

/**
 * "No agent can run this": the agents text-to-cad offers first, each with
 * its Install / Sign in, and the way to the rest in Settings › Agents. The
 * new-session screen shows it before anything is typed when no agent is
 * ready; a session whose agent's CLI is gone shows it in place of a
 * Reconnect that would only fail again. An agent one sign-in away is listed
 * first, so the first button is that sign-in rather than an install.
 */
export function AgentSetupCard({
  agents,
  title,
  message,
  onRetry,
}: {
  agents: AgentStatus[];
  title: string;
  message: string;
  /** A promise is waited on: the button says it is trying, and a try that fails the same way says so. */
  onRetry?: () => void | Promise<unknown>;
}) {
  const openSettings = useUi((state) => state.openSettings);
  // A Try again whose answer is the same error redraws the same words, which reads as a button
  // that did nothing: the try is shown while it runs, and a card still here after it says so.
  const [trying, setTrying] = useState(false);
  const [tries, setTries] = useState(0);
  const mounted = useRef(true);
  useEffect(() => () => {
    mounted.current = false;
  }, []);
  const retry = async () => {
    if (!onRetry || trying) return;
    setTrying(true);
    try {
      await onRetry();
    } finally {
      if (mounted.current) {
        setTrying(false);
        setTries((count) => count + 1);
      }
    }
  };
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card px-4 py-3" data-agent-setup>
      <div>
        <p className="text-[13px] font-medium">{title}</p>
        <p className="mt-0.5 text-[13px] leading-5 whitespace-pre-wrap text-muted-foreground">{message}</p>
        {tries > 0 && !trying ? (
          <p className="mt-1 text-[12px] text-muted-foreground" data-retry-result role="status">
            {tries === 1 ? "Tried again, and it failed again." : `Tried again ${tries} times, and it failed each time.`}
          </p>
        ) : null}
      </div>
      {agents.length > 0 ? (
        <div className="space-y-2">
          {[...agents.filter(canSignIn), ...agents.filter((agent) => !canSignIn(agent))].map((agent) => (
            <AgentRow agent={agent} key={agent.id} />
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {onRetry ? (
          <Button aria-busy={trying || undefined} className="h-7 gap-1.5 text-[12px]" disabled={trying} onClick={() => void retry()} size="sm" variant="outline">
            {trying ? <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" /> : <RotateCcw className="size-3.5" />}
            {trying ? "Trying again…" : "Try again"}
          </Button>
        ) : null}
        <Button
          className="h-7 text-[12px] text-muted-foreground"
          onClick={() => openSettings("agents")}
          size="sm"
          variant="ghost"
        >
          Settings › Agents
        </Button>
      </div>
    </div>
  );
}

/** The agents offered first (the welcome's order), as detection reported them. */
export function useOfferedAgents(): AgentStatus[] {
  const agents = useAgents((state) => state.agents);
  return ONBOARDING_AGENT_IDS.map((id) => agents.find((agent) => agent.id === id)).filter(
    (agent): agent is AgentStatus => agent !== undefined,
  );
}
