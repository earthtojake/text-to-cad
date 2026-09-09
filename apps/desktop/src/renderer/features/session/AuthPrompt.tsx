import { useEffect, useRef, useState } from "react";
import { KeyRound, Loader2, RotateCcw } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { useAgents } from "@renderer/state/agents";
import { useUi } from "@renderer/state/ui";
import type { AgentStatus } from "@shared/agents";

/**
 * The authenticating state: the agent answered "sign in first". The
 * agent's own login method is the action — `codex login`, `claude auth
 * login` — run in a pty by main, its output shown here so a device code or
 * a URL is not lost. When the job ends the caller's retry re-creates the
 * session.
 */
export function AuthPrompt({
  agent,
  message,
  onRetry,
}: {
  agent: AgentStatus | null;
  message: string | null;
  onRetry: () => void;
}) {
  const login = useAgents((state) => state.login);
  const jobs = useAgents((state) => state.jobs);
  const openSettings = useUi((state) => state.openSettings);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = jobId ? (jobs[jobId] ?? null) : null;
  const running = job !== null && job.exitCode === null;
  const outputRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    outputRef.current?.scrollTo({ top: outputRef.current.scrollHeight });
  }, [job?.output]);

  const cliLogin = agent?.authMethods.find((method) => method.type === "cli-login") ?? null;
  const apiKey = agent?.authMethods.find((method) => method.type === "api-key") ?? null;

  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-col gap-3 px-6 py-8" data-auth-prompt>
      <div className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <KeyRound className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium">
            {agent ? `Sign in to ${agent.name}` : "Sign in to the agent"}
          </p>
          <p className="mt-0.5 text-[13px] leading-5 text-muted-foreground">
            {message ?? "The agent needs an account before it can start a session."}
          </p>
          {apiKey ? (
            <p className="mt-0.5 text-[12px] leading-5 text-muted-foreground/80">
              Or set {apiKey.envVars.join(" or ")} in your shell and try again.
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {cliLogin && agent ? (
              <Button
                className="h-7 gap-1.5 text-[12px]"
                disabled={running}
                onClick={() => void login(agent.id).then(setJobId)}
                size="sm"
              >
                {running ? <Loader2 className="size-3.5 animate-spin" /> : <KeyRound className="size-3.5" />}
                {cliLogin.label}
              </Button>
            ) : null}
            <Button className="h-7 gap-1.5 text-[12px]" onClick={onRetry} size="sm" variant="outline">
              <RotateCcw className="size-3.5" />
              Try again
            </Button>
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
      </div>
      {job ? (
        <pre
          className="max-h-56 overflow-auto rounded-xl border bg-muted/40 px-3 py-2 font-mono text-[12px] leading-5 whitespace-pre-wrap select-text"
          ref={outputRef}
        >
          {job.output || (running ? "Starting…" : "")}
          {job.exitCode !== null ? `\n[exited with ${job.exitCode}]` : ""}
        </pre>
      ) : null}
    </div>
  );
}
