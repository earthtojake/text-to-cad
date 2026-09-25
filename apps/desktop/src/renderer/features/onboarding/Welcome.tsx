import { useEffect, useState } from "react";
import { ArrowRight, Box, Check, FolderOpen, Loader2 } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { AgentMark } from "@renderer/features/settings/AgentMark";
import { JobLog, useJob } from "@renderer/features/settings/AgentDrawer";
import { useOpenFolder } from "@renderer/hooks/use-open-folder";
import { cn } from "@renderer/lib/utils";
import { useAgents } from "@renderer/state/agents";
import { ONBOARDING_AGENT_IDS } from "@renderer/state/onboarding";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import type { AgentStatus } from "@shared/agents";
import hardcoreMark from "@renderer/assets/brand/hardcore-star.svg";

/**
 * The first-run welcome: three short steps over the whole window, shown once.
 * Finishing or skipping it sets `onboardingCompleted`, and the sidebar's
 * Getting started checklist picks up from there.
 */
export function Welcome() {
  const [step, setStep] = useState(0);
  const patch = useSettings((state) => state.patch);
  const finish = () => void patch({ onboardingCompleted: true });

  return (
    <div className="flex h-full flex-col bg-background" data-onboarding>
      {/* The window's drag strip; the traffic lights sit in its left inset. */}
      <div className="app-drag h-10 shrink-0" />
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto px-6 pb-10">
        <div className="w-full max-w-md">
          {step === 0 ? <WelcomeStep /> : step === 1 ? <AgentStep /> : <StartStep onDone={finish} />}

          <div className="mt-8 flex items-center justify-between">
            <StepDots count={3} current={step} />
            <div className="flex items-center gap-2">
              {step > 0 ? (
                <Button className="text-muted-foreground" onClick={() => setStep(step - 1)} size="sm" variant="ghost">
                  Back
                </Button>
              ) : null}
              <Button className="text-muted-foreground" onClick={finish} size="sm" variant="ghost">
                Skip for now
              </Button>
              {step < 2 ? (
                <Button className="gap-1.5" onClick={() => setStep(step + 1)} size="sm">
                  Continue
                  <ArrowRight className="size-3.5" />
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function WelcomeStep() {
  return (
    <section aria-labelledby="onboarding-title">
      <img alt="" className="size-12 object-contain" src={hardcoreMark} />
      <h1 className="mt-5 text-2xl font-medium tracking-tight" id="onboarding-title">
        Welcome to Hardcore
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Describe a part and an AI agent builds it as real CAD you can open, measure and export.
      </p>
      <ul className="mt-6 space-y-3 text-sm">
        <Point title="Chat on the left">The agent writes a script and builds the part in your folder.</Point>
        <Point title="Model on the right">Every STEP, STL and drawing opens in the built-in viewer.</Point>
        <Point title="Point at what to change">Select a face or edge and send it to the chat.</Point>
      </ul>
    </section>
  );
}

function Point({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <Check className="mt-0.5 size-4 shrink-0 text-primary" />
      <span>
        <span className="font-medium">{title}.</span> <span className="text-muted-foreground">{children}</span>
      </span>
    </li>
  );
}

function AgentStep() {
  const agents = useAgents((state) => state.agents);
  const offered = ONBOARDING_AGENT_IDS.map((id) => agents.find((agent) => agent.id === id)).filter(
    (agent): agent is AgentStatus => agent !== undefined,
  );
  const openSettings = useUi((state) => state.openSettings);

  return (
    <section aria-labelledby="onboarding-agent-title">
      <h1 className="text-2xl font-medium tracking-tight" id="onboarding-agent-title">
        Connect an agent
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Hardcore runs the coding agent you already use. You need one of these, installed and signed in.
      </p>
      <div className="mt-6 space-y-2">
        {offered.map((agent) => (
          <AgentRow agent={agent} key={agent.id} />
        ))}
      </div>
      <button
        className="mt-3 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        onClick={() => openSettings("agents")}
        type="button"
      >
        Use a different agent in Settings › Agents
      </button>
    </section>
  );
}

function AgentRow({ agent }: { agent: AgentStatus }) {
  const install = useAgents((state) => state.install);
  const login = useAgents((state) => state.login);
  const refresh = useAgents((state) => state.refresh);
  const { jobId, output, running, start } = useJob();

  // An install or sign-in changes what detection would find: look again once it ends.
  useEffect(() => {
    if (jobId && !running) {
      void refresh();
    }
  }, [jobId, running, refresh]);

  const ready = agent.installed && (agent.auth === "authenticated" || agent.auth === "not-required");
  const status = ready ? "Ready" : !agent.installed ? "Not installed" : agent.auth === "unauthenticated" ? "Signed out" : "Installed";

  return (
    <div className="rounded-lg border px-3 py-2.5" data-onboarding-agent={agent.id}>
      <div className="flex items-center gap-3">
        <AgentMark icon={agent.icon} id={agent.id} name={agent.name} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{agent.name}</p>
          <p className={cn("text-xs", ready ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground")}>
            {status}
          </p>
        </div>
        {ready ? (
          <Check aria-label="Ready" className="size-4 text-emerald-500" />
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
      {jobId ? <JobLog output={output} /> : null}
    </div>
  );
}

function StartStep({ onDone }: { onDone: () => void }) {
  const openFolder = useOpenFolder();
  const [busy, setBusy] = useState<"sample" | "folder" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const trySample = async () => {
    setBusy("sample");
    setError(null);
    try {
      const { path } = await window.hardcore.onboarding.createSample();
      // Main broadcasts the selection, which opens the folder's new-session screen.
      await window.hardcore.projects.addPath({ path });
      onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(null);
    }
  };

  const chooseFolder = async () => {
    setBusy("folder");
    setError(null);
    try {
      if (await openFolder()) {
        onDone();
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-labelledby="onboarding-start-title">
      <h1 className="text-2xl font-medium tracking-tight" id="onboarding-start-title">
        Where do you want to start?
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        A session always belongs to a folder. The agent reads and writes files there.
      </p>
      <div className="mt-6 grid gap-2">
        <StartOption
          busy={busy === "sample"}
          description="An L-bracket to open, change and export. Copied to Documents › Hardcore Sample."
          disabled={busy !== null}
          icon={<Box className="size-4" />}
          onClick={() => void trySample()}
          title="Try the sample"
        />
        <StartOption
          busy={busy === "folder"}
          description="Start in a folder of your own, empty or not."
          disabled={busy !== null}
          icon={<FolderOpen className="size-4" />}
          onClick={() => void chooseFolder()}
          title="Open a folder…"
        />
      </div>
      {error ? <p className="mt-3 text-xs text-destructive">{error}</p> : null}
    </section>
  );
}

function StartOption({
  title,
  description,
  icon,
  busy,
  disabled,
  onClick,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="flex items-start gap-3 rounded-lg border px-3 py-3 text-left transition-colors hover:bg-muted/60 disabled:opacity-60"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <span className="mt-0.5 text-muted-foreground">{busy ? <Loader2 className="size-4 animate-spin" /> : icon}</span>
      <span>
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs text-muted-foreground">{description}</span>
      </span>
    </button>
  );
}

function StepDots({ count, current }: { count: number; current: number }) {
  return (
    <div aria-label={`Step ${current + 1} of ${count}`} className="flex items-center gap-1.5" role="img">
      {Array.from({ length: count }, (_, index) => (
        <span
          className={cn("size-1.5 rounded-full", index === current ? "bg-foreground" : "bg-muted-foreground/30")}
          key={index}
        />
      ))}
    </div>
  );
}
