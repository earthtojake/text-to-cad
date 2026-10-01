import { useEffect, useRef, useState } from "react";
import { ArrowRight, Box, Check, FolderOpen, Loader2 } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { AgentRow, isAgentReady, useOfferedAgents } from "@renderer/features/session/agent-setup";
import { useOpenFolder } from "@renderer/hooks/use-open-folder";
import { cn } from "@renderer/lib/utils";
import { useAgents, useAgentsProbing } from "@renderer/state/agents";
import { useOnboarding } from "@renderer/state/onboarding";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import textToCadMark from "@renderer/assets/brand/text-to-cad-star.svg";

/**
 * The first-run welcome: three short steps over the whole window, shown once.
 * Finishing or skipping it sets `onboardingCompleted`, and the sidebar's
 * Getting started checklist picks up from there.
 */
export function Welcome() {
  const step = useOnboarding((state) => state.step);
  const setStep = useOnboarding((state) => state.setStep);
  const patch = useSettings((state) => state.patch);
  const finish = () => void patch({ onboardingCompleted: true });
  // On the agent step, Continue says what it means when nothing can run yet:
  // the rest of the app opens, but a session will not start until one is.
  // Cautious on purpose: unknown sign-in is not ready here (see `isAgentReady`).
  // Until detection answers, nothing is known either way: the button stays
  // "Continue", disabled, rather than announcing "without an agent" for the
  // second or two before one turns up.
  const anyAgentReady = useAgents((state) => state.agents.some(isAgentReady));
  const detected = useAgents((state) => state.ready);
  // A warm launch answers with the last launch's rows (`probing`), whose verdicts are provisional:
  // the button waits for `agents.status` the same way it waits for a first answer.
  const probing = useAgentsProbing();
  const detecting = step === 1 && (!detected || probing);
  const continueLabel =
    step === 1 && detected && probing ? "Checking…" : step === 1 && detected && !anyAgentReady ? "Continue without an agent" : "Continue";
  // A new step takes focus to its heading, which is read out with the step. The button that moved
  // it can go with the step (Continue is not on the last) or be disabled by it (Continue while
  // detection runs), and focus on either fell to the page.
  const bodyRef = useRef<HTMLElement | null>(null);
  const shownStep = useRef(step);
  useEffect(() => {
    if (shownStep.current === step) return;
    shownStep.current = step;
    bodyRef.current?.querySelector<HTMLElement>("h1")?.focus();
  }, [step]);

  return (
    <div className="flex h-full flex-col bg-background" data-onboarding>
      {/* The welcome replaces the shell, so this strip is the window's top
          edge: the title bar's height, with the traffic lights' corner
          reserved the same way Settings' header reserves it. */}
      <div
        className="app-drag shrink-0"
        data-onboarding-titlebar
        style={{ height: "var(--titlebar-height)", paddingLeft: "var(--titlebar-inset)" }}
      />
      {/* The block's top is pinned, not centred: the steps are different
          heights, and a centred block moved its heading ~70px each step. */}
      <main className="flex min-h-0 flex-1 justify-center overflow-auto px-6 pt-[22vh] pb-10" data-onboarding-body ref={bodyRef}>
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
                <Button className="gap-1.5" disabled={detecting} onClick={() => setStep(step + 1)} size="sm">
                  {continueLabel}
                  <ArrowRight className="size-3.5" />
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function WelcomeStep() {
  return (
    <section aria-labelledby="onboarding-title">
      <img alt="" className="size-12 object-contain" src={textToCadMark} />
      <h1 className="mt-5 text-2xl font-medium tracking-tight outline-none" id="onboarding-title" tabIndex={-1}>
        Welcome to text-to-cad
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Describe a part and an AI agent builds it as real CAD you can open, measure and export.
      </p>
      <ul className="mt-6 space-y-3 text-sm">
        <Point title="Session in the middle">The agent writes a script and builds the part in your folder.</Point>
        <Point title="Model on the right">Every STEP, STL and drawing opens in the built-in viewer.</Point>
        <Point title="Point at what to change">Select a face or edge and Annotate it.</Point>
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
  const detected = useAgents((state) => state.ready);
  const loadError = useAgents((state) => state.loadError);
  const offered = useOfferedAgents();
  const openSettings = useUi((state) => state.openSettings);

  return (
    <section aria-labelledby="onboarding-agent-title">
      <h1 className="text-2xl font-medium tracking-tight outline-none" id="onboarding-agent-title" tabIndex={-1}>
        Connect an agent
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        text-to-cad runs the coding agent you already use. You need one of these, installed and signed in.
      </p>
      <div className="mt-6 space-y-2">
        {loadError ? (
          <p className="text-sm text-destructive" role="alert">
            Could not read the agent list: {loadError}
          </p>
        ) : null}
        {!detected && offered.length === 0 ? (
          <p className="text-sm text-muted-foreground" role="status">
            Looking for agents on this machine…
          </p>
        ) : null}
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

function StartStep({ onDone }: { onDone: () => void }) {
  const openFolder = useOpenFolder();
  const [busy, setBusy] = useState<"sample" | "folder" | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Back while the sample copies unmounts this step: the person has moved
  // on, and the copy finishing must neither select the sample nor finish the
  // welcome behind them. (The copy itself completes; it is left on disk.)
  const here = useRef(true);
  useEffect(() => {
    here.current = true;
    return () => {
      here.current = false;
    };
  }, []);

  const trySample = async () => {
    setBusy("sample");
    setError(null);
    try {
      // Main copies the sample and answers with it; selecting it here, as
      // `ui.directorySelected` would, opens the folder's new-session screen.
      const sample = await window.textToCad.onboarding.createSample();
      if (here.current) {
        useProjects.getState().selectDirectory(sample);
        useSessions.getState().setActive(null);
        onDone();
      }
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
      if ((await openFolder()) && here.current) {
        onDone();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-labelledby="onboarding-start-title">
      <h1 className="text-2xl font-medium tracking-tight outline-none" id="onboarding-start-title" tabIndex={-1}>
        Where do you want to start?
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        A session always belongs to a folder. The agent reads and writes files there.
      </p>
      <div className="mt-6 grid gap-2">
        <StartOption
          busy={busy === "sample"}
          description="An L-bracket to open, change and export. Copied to Documents › text-to-cad Sample."
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
      {error ? (
        <p className="mt-3 text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : null}
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
