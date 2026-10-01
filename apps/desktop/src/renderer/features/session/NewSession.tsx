import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { AlertCircle, Loader2, RotateCcw, Settings2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@renderer/components/ui/button";
import { resolveGitMode, useProjectGitInfo } from "@renderer/lib/git-mode";
import { useAcp } from "@renderer/state/acp";
import {
  useAgentOptions,
  useProviderEffort,
  useProviderMode,
  useProviderModels,
} from "@renderer/state/agent-options";
import { useAgents, useAgentsProbing, useInstalledAgents } from "@renderer/state/agents";
import { newSessionKey, useComposer, type TakenDraft } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import type { PromptBlock } from "@shared/acp/types";
import { isDeletedWhileStarting } from "@shared/ipc/errors";
import type { AgentStatus } from "@shared/agents";
import type { GitMode, Project } from "@shared/types";

import { AgentSetupCard, useOfferedAgents } from "./agent-setup";
import { AuthPrompt } from "./AuthPrompt";
import { Composer } from "./Composer";
import { EffortChip, GitModeChip, ModeChip, ModelChip, ProjectChip } from "./ComposerChips";
import { errorMessage, isAuthError } from "./view";

/**
 * The new-session state (plan §2): "What should we build in <project>?",
 * a line saying what a session is, the context strip — project · git mode —
 * and an empty composer with `+`, the mode, the model and the effort in the
 * row under its box. Nothing
 * else: a grid of canned prompts under the box is four guesses at what
 * somebody came here to do. Sending creates the session — `sessions.create`
 * spawns the agent — selects it, and sends the first prompt; the transcript
 * takes over from there.
 *
 * **The model chip is the agent chip.** Picking `Opus` picks Claude Code and
 * picking `GPT-6-Astra` picks Codex, because that is the decision somebody
 * is actually making; a menu of vendors above a menu of their models is the
 * same choice asked twice. The models come from each installed agent's last
 * `session/new` reply, cached per agent and probed once for an agent nobody
 * has run yet (`state/agent-options.ts`), so a provider that is not
 * installed — or not signed in, or whose adapter will not start — contributes
 * no models rather than models that cannot be run.
 *
 * **The mode chip is the permission control**, here as in a live thread: the
 * mode this session will be created in, from the same cached snapshot,
 * starting at the provider's own auto-approval preset until somebody picks
 * something else. There is no second, app-side approval setting — what the
 * agent asks about is what its mode says, and a request that arrives is
 * answered in the transcript.
 *
 * Creation can fail before there is a session to show it in: the agent is
 * not signed in, or its adapter would not start. Those land here, above
 * the composer, with the agent's login as the action — or Settings › Agents
 * for anything else. A machine with no agent ready says so before anything
 * is typed, with the sign-in or the install as the action, rather than
 * after a send.
 */
export function NewSession({ project }: { project: Project }) {
  const draftKey = newSessionKey(project.id);
  const draftRoot = useComposer((state) => state.draftRoots[draftKey]);
  const settings = useSettings((state) => state.settings);
  const agents = useAgents((state) => state.agents);
  const installed = useInstalledAgents();
  const detected = useAgents((state) => state.ready);
  const tableProbing = useAgentsProbing();
  const listError = useAgents((state) => state.loadError);
  const reloadAgents = useAgents((state) => state.load);
  const offered = useOfferedAgents();
  const openSettings = useUi((state) => state.openSettings);
  const setActiveProject = useProjects((state) => state.setActive);
  const setActiveSession = useSessions((state) => state.setActive);
  const create = useAcp((state) => state.create);
  const submitPrompt = useComposer((state) => state.submit);
  const probeOptions = useAgentOptions((state) => state.probe);
  const setAgentDefaults = useAgentOptions((state) => state.setDefaults);
  const setAgentEffort = useAgentOptions((state) => state.setEffort);

  const [agentId, setAgentId] = useState<string | null>(null);
  const [gitMode, setGitMode] = useState<GitMode | null>(null);
  const [busy, setBusy] = useState(false);
  // A send held because the first probe has not said which agents are installed.
  const [checking, setChecking] = useState(false);
  const [failure, setFailure] = useState<{ message: string; auth: boolean } | null>(null);
  // The draft the failed start took from the box, as the composer put it back. "Try again" sends
  // what the box holds *now* — the person may have edited it since — and a sign-in that finishes
  // retries by itself only while the box still holds exactly this.
  const failedAttempt = useRef<TakenDraft | null>(null);
  // Whether there is an attempt to retry, for the card: Try again is drawn only then, so it never
  // stands in for Dismiss (the ref is not something a render may read).
  const [retryable, setRetryable] = useState(false);
  // The agent the last start actually tried to create with: a held send resolves it only when the
  // probe lands, after the render whose closure `submitFromComposer` runs in, so neither
  // "Try again" nor the sign-in flag may be read from that closure's `startingAgentId`.
  const triedAgentId = useRef<string | null>(null);
  // A create takes seconds, and the person may click the connecting row in the sidebar meanwhile:
  // this screen unmounts, and the card `failure` would draw goes nowhere.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const jobs = useAgents((state) => state.jobs);

  // Defaults come from settings and from what is installed; a choice made
  // here sticks until the session is created.
  // Settings' default agent, else the first installed one that is signed
  // in, else the first installed one — a signed-out agent is one click away
  // but should not be the first thing a new user sends a prompt to.
  const resolvedAgentId =
    agentId ??
    (settings?.defaultAgentId && installed.some((agent) => agent.id === settings.defaultAgentId)
      ? settings.defaultAgentId
      : (installed.find((agent) => agent.auth !== "unauthenticated")?.id ?? installed[0]?.id ?? null));
  // Two choices, Local and New worktree (plan §9, `lib/git-mode.ts`): which
  // `GitMode` "Local" means is the project's business, not the person's — a
  // folder that is not a repository has no checkout to work in.
  const gitInfo = useProjectGitInfo(project.id);
  const resolvedGitMode = resolveGitMode(gitMode ?? settings?.defaultGitMode ?? "checkout", gitInfo);

  // Every installed agent is asked for a snapshot the first time this screen
  // is looked at. Main answers from its cache when it has one and spawns a
  // single probe when it does not, so this is a no-op after the first run.
  // An adapter-only agent whose CLI is not here is asked too, and main
  // answers at once without spawning (`SessionManager.canProbe`): only main
  // knows when the fake agent's launch override makes it probeable anyway.
  // Which of those probes are still out: the model chip says "Loading
  // models…" while one is, rather than being absent. Counted per set of
  // agents and project, so a new round starts from none answered.
  const installedIds = installed.map((candidate) => candidate.id).join(",");
  const probeRound = `${project.id}|${installedIds}`;
  const [answered, setAnswered] = useState<{ round: string; count: number }>({ round: "", count: 0 });
  useEffect(() => {
    let live = true;
    for (const id of installedIds.split(",").filter(Boolean)) {
      void Promise.resolve(probeOptions(id, project.id))
        .catch(() => {})
        .finally(() => {
          if (!live) return;
          setAnswered((previous) =>
            previous.round === probeRound ? { round: probeRound, count: previous.count + 1 } : { round: probeRound, count: 1 },
          );
        });
    }
    return () => {
      live = false;
    };
  }, [installedIds, probeRound, project.id, probeOptions]);
  const probing = installed.length - (answered.round === probeRound ? answered.count : 0);

  // The models of every installed agent that has answered, and the effort
  // levels of whichever one is picked. `providers` decides which agent the
  // session runs: an agent with no models in the menu is one nobody can pick.
  const providers = useProviderModels(installed);
  const pickedProvider =
    providers.find((provider) => provider.agentId === resolvedAgentId) ?? providers[0] ?? null;
  // The model the chip is showing — this provider's remembered one, else the
  // model it reported as current. The effort is remembered against that
  // model, and its levels are that model's, so switching the model chip
  // swaps the effort chip's list and its value in one step.
  const pickedModel = pickedProvider?.model.currentValue ?? null;
  const effort = useProviderEffort(pickedProvider?.agentId ?? null, pickedModel);
  // The mode the session will be created in: this agent's stored default,
  // else its own auto-approval preset — which is what main applies right
  // after `session/new` (`applyPreferences`), so the chip is a statement
  // about what will happen rather than a control that has to be wired
  // through `create`.
  const mode = useProviderMode(pickedProvider?.agentId ?? null);
  // Who will actually run this: the model chip's provider, because that is
  // the choice the person made. Everything that names the agent — the
  // placeholder, the sign-in prompt when creation fails — names this one.
  const startingAgentId = pickedProvider?.agentId ?? resolvedAgentId;
  const agent = agents.find((candidate) => candidate.id === startingAgentId) ?? null;

  // Picking a model under another provider swaps provider: its remembered
  // effort and mode come with it, because both are read against the agent the
  // chips are showing. Nothing here touches the efforts — the level chosen
  // under the model being left is still that model's.
  const chooseModel = (pickedAgentId: string, value: string) => {
    setAgentId(pickedAgentId);
    setFailure(null);
    void setAgentDefaults(pickedAgentId, { model: value });
  };

  const chooseEffort = (_configId: string, value: string) => {
    if (!pickedProvider) {
      return;
    }
    // Pinned to the agent the chips are showing, the way picking a model or a
    // mode pins it: which agent this screen starts with is otherwise still
    // moving while the detector answers each one's login, and an effort
    // stored against whoever was showing at the click is an effort nobody
    // chose. Keyed by the model it was chosen under, which is that same chip.
    setAgentId(pickedProvider.agentId);
    void setAgentEffort(pickedProvider.agentId, pickedProvider.model.currentValue, value);
  };

  const chooseMode = (modeId: string) => {
    if (!pickedProvider) {
      return;
    }
    // Pinned to the agent the chips are showing, the way picking a model
    // pins it. Which agent this screen starts with is otherwise still
    // moving — the detector answers each one's login in its own time, and
    // `resolvedAgentId` follows it — so a mode stored against whoever was
    // showing at the click and a session created with whoever is showing at
    // send is a session in a mode nobody chose.
    setAgentId(pickedProvider.agentId);
    void setAgentDefaults(pickedProvider.agentId, { mode: modeId });
  };

  /**
   * Whether the session started. What the box held is not put back here: the composer took it
   * whole on submit — the typed text and the annotations apart — and restores it when
   * `submitFromComposer` rejects. Writing the prompt back into the draft here would write the
   * annotations into the text, as a list, a second time beside their own chip.
   */
  const start = async (text: string, content: PromptBlock[], draft: TakenDraft): Promise<boolean> => {
    let chosenAgentId = startingAgentId;
    triedAgentId.current = null;
    if (!chosenAgentId && !useAgents.getState().ready) {
      // An empty table before the first probe has landed is "not checked yet", not "nothing
      // installed": the send is held, and goes out (or is refused) once detection has answered.
      setBusy(true);
      setChecking(true);
      await agentsReady();
      if (mounted.current) setChecking(false);
      const answered = useAgents.getState();
      if (answered.loadError) {
        // Every row's probe failed: the check did not happen, which is not "nothing installed".
        // The send is released; the "Could not check for agents" card (with its Retry) says why.
        if (mounted.current) setBusy(false);
        return false;
      }
      chosenAgentId = firstAgentId(answered.agents, useSettings.getState().settings?.defaultAgentId ?? null);
      if (!chosenAgentId && mounted.current) setBusy(false);
    }
    if (!chosenAgentId) {
      setFailure({ message: "Install an agent first — Settings › Agents lists what text-to-cad can run.", auth: false });
      return false;
    }
    setBusy(true);
    setFailure(null);
    triedAgentId.current = chosenAgentId;
    const usedAgent = useAgents.getState().agents.find((candidate) => candidate.id === chosenAgentId);
    let sessionId: string;
    try {
      // The model, the effort and the mode are not passed: they are this
      // agent's stored defaults, and main applies them to the session it
      // just created — in that order, because the model decides which
      // efforts exist.
      sessionId = await create({
        projectId: project.id,
        agentId: chosenAgentId,
        ...(draftRoot ? { cwd: draftRoot } : {}),
        gitMode: resolvedGitMode,
      });
    } catch (error) {
      const message = errorMessage(error);
      if (isDeletedWhileStarting(message)) {
        // The person deleted the connecting row: nothing failed, so no card and no toast. The
        // composer puts the draft back on the false.
        if (mounted.current) setBusy(false);
        return false;
      }
      if (!mounted.current) {
        // The person is elsewhere (the connecting row, or another thread): say so where they are.
        // The composer has already put the draft back (`restoreDraft`), so Try again is the way
        // back to the new-session screen that holds it.
        toast.error(message, {
          action: {
            label: "Try again",
            onClick: () => {
              useProjects.getState().setActive(project.id);
              useSessions.getState().setActive(null);
            },
          },
        });
        return false;
      }
      // Main has already dropped the row: nothing to resume, nothing to list.
      setFailure({ message, auth: isAuthError(message) || usedAgent?.auth === "unauthenticated" });
      setBusy(false);
      return false;
    }
    failedAttempt.current = null;
    setRetryable(false);
    // Archived while the create ran: the person put the thread away, so it is
    // neither opened nor sent to (main refuses the prompt to a row it would
    // have to reconnect). What was written waits in that thread's box, which
    // an archived row keeps.
    if (useSessions.getState().sessions.find((row) => row.id === sessionId)?.archived) {
      useComposer.getState().restoreDraft(sessionId, draft);
      setBusy(false);
      return true;
    }
    // Only from the screen the person is still on (or the connecting row this create made): a
    // create that outlasted a click on another thread does not pull them back, nor does one
    // that outlasted a move to another project's new-session screen (`activeId` is null there
    // too, with this screen unmounted).
    const activeNow = useSessions.getState().activeId;
    if (activeNow === sessionId || (activeNow === null && mounted.current)) {
      setActiveSession(sessionId);
    }
    setBusy(false);
    // The prompt goes to the session just made, whose box is the one on screen from here on. An
    // agent that refuses it (an image it cannot take), or main refusing it before any turn (the
    // agent would not start), refuses it after this box has gone, so what was written —
    // attachments included — is put back in that one rather than spent. `submit` rejects for
    // nothing else: a turn that began and failed is in the transcript with its Retry.
    submitPrompt(sessionId, text, content, draft).catch(() => {
      useComposer.getState().restoreDraft(sessionId, draft);
    });
    return true;
  };

  // The composer's send: a start that fails rejects, and the composer puts its draft back.
  const submitFromComposer = async (text: string, content: PromptBlock[], draft: TakenDraft) => {
    if (!(await start(text, content, draft))) {
      failedAttempt.current = draft;
      // "Install an agent first" is not a failed attempt: nothing was tried, and its card has Dismiss.
      setRetryable(Boolean(triedAgentId.current));
      throw new Error("The session did not start");
    }
  };

  // Try again is the composer's own send of what the box holds now — edited or not, attachments
  // and annotations included — so the draft is taken, and put back on another failure, by the one
  // path that already does both. Nothing here clears the box.
  // A box the person has emptied since the failure holds nothing to send, so the last attempt's
  // text and notes go back in first: Try again retries the last form values, never nothing.
  const retry = () => {
    const attempt = failedAttempt.current;
    if (busy || !attempt) return;
    const composer = useComposer.getState();
    const boxEmpty = !(composer.drafts[draftKey] ?? "").trim() && !(composer.annotations[draftKey]?.length ?? 0);
    if (boxEmpty) {
      // Its files are the strip's own: the composer put them back when the start failed.
      const { files: _files, ...withoutFiles } = attempt;
      composer.restoreDraft(draftKey, withoutFiles);
    }
    composer.requestSubmit(draftKey);
  };

  // A sign-in retries only the prompt that failed: a box edited since is the person's next draft,
  // left for them to send.
  const retryAfterSignIn = () => {
    const attempt = failedAttempt.current;
    if (!attempt || !unchangedSince(attempt, draftKey)) return;
    retry();
  };

  // A sign-in that finishes is the retry: when a login job for this agent
  // that was not already over when the prompt appeared exits 0, start again.
  // `settledLogins` is what had already ended when the prompt went up, so a
  // login from an earlier failure does not fire this one.
  const settledLogins = useRef<Set<string> | null>(null);
  const retryAfterLogin = useEffectEvent(retryAfterSignIn);
  useEffect(() => {
    if (!failure?.auth || !startingAgentId) {
      settledLogins.current = null;
      return;
    }
    const ended = Object.entries(jobs).filter(
      ([, job]) => job.kind === "login" && job.agentId === startingAgentId && job.exitCode !== null,
    );
    if (!settledLogins.current) {
      settledLogins.current = new Set(ended.map(([id]) => id));
      return;
    }
    const seen = settledLogins.current;
    const fresh = ended.filter(([id]) => !seen.has(id));
    for (const [id] of fresh) seen.add(id);
    if (fresh.some(([, job]) => job.exitCode === 0)) {
      retryAfterLogin();
    }
  }, [failure, jobs, startingAgentId]);

  // What the session will be, as a strip above the box: where it runs, how
  // it treats git — the two things that cannot change once the session
  // exists, so they sit above the box. Under the box is the live session's
  // row exactly: `+` and the mode on the left, the model and the effort on
  // the right, so the two screens are one shape and a long model name has
  // the row's width rather than the strip's.
  const context = (
    <div className="mb-1.5 flex items-center gap-1 px-1" data-context-strip>
      <ProjectChip onChange={setActiveProject} project={project} />
      <Dot />
      {draftRoot ? (
        // The folder's name, with its whole path as the hover hint and what a screen reader hears.
        <TooltipHint content={draftRoot}>
          <span className="text-xs text-muted-foreground" data-draft-root>
            In <span aria-hidden>{draftRoot.split(/[\\/]/).pop()}</span>
            <span className="sr-only">{draftRoot}</span>
          </span>
        </TooltipHint>
      ) : <GitModeChip gitMode={resolvedGitMode} info={gitInfo} onChange={setGitMode} />}
    </div>
  );
  // Detection has answered and every agent that can launch is known to be
  // signed out. Not "none installed" — Claude Code and Codex launch without
  // their CLI (`useInstalledAgents` counts them) — and not "none signed in":
  // detection says "unknown" whenever it has no env var, check command or
  // credentials file to go by (Copilot and Kiro always; Claude Code in the
  // keychain), and such an agent may well work. So only "unauthenticated"
  // counts against an agent here, the same test the default pick above uses.
  // A table still `probing` is the last launch's: its "signed out" is not yet
  // an answer, and the chips draw from it meanwhile.
  // A list that could not be read is not a list of signed-out agents: it
  // says what failed and offers the read again, rather than asking for a
  // sign-in nobody can see a reason for.
  const noAgent = detected && !listError && !tableProbing && !installed.some((candidate) => candidate.auth !== "unauthenticated");
  // Either way nothing can start a session from here, so the chips are shown
  // as they are and not offered, and a send says why instead of going out.
  const unavailable = listError ? "The agent list could not be read" : noAgent ? "No agent ready — sign in to one first" : undefined;
  const offeredNames = offered.map((candidate) => candidate.name);
  const signInTo = offeredNames.length > 0 ? offeredNames.join(" or ") : "an agent";
  // Until detection has answered and some probe has come back, all three
  // slots hold a placeholder of the chip's size: chips that pop in seconds
  // later, one by one, are a row that jumps under the pointer.
  const loadingChips = providers.length === 0 && (!detected || probing > 0);
  const chips = mode ? (
    <ModeChip currentModeId={mode.currentModeId} disabledReason={unavailable} modes={mode.modes} onChange={chooseMode} />
  ) : loadingChips ? (
    <ChipSkeleton slot="mode" width="w-16" />
  ) : null;
  const trailing = (
    <>
      {providers.length > 0 ? (
        <ModelChip agentId={pickedProvider?.agentId ?? null} disabledReason={unavailable} onChange={chooseModel} providers={providers} />
      ) : loadingChips ? (
        <ModelsLoading />
      ) : null}
      {effort ? (
        <EffortChip disabledReason={unavailable} effort={effort} onChange={chooseEffort} />
      ) : loadingChips ? (
        <ChipSkeleton slot="effort" width="w-20" />
      ) : null}
    </>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-6 pb-10" data-new-session>
      <div className="w-full max-w-[720px]">
        <h1 className="text-center text-[22px] leading-tight font-medium tracking-tight text-balance">
          What should we build in {project.name}?
        </h1>
        <p className="mt-2 text-center text-[13px] text-balance text-muted-foreground">
          text-to-cad runs the agent in this folder, with cadgen and the CAD skills already loaded.
        </p>

        {failure?.auth ? (
          <div className="mt-4">
            <AuthPrompt agent={agent} message={failure.message} onRetry={retry} />
          </div>
        ) : failure ? (
          <div
            className="mt-4 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] leading-5"
            role="alert"
          >
            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
            <div className="min-w-0 flex-1 whitespace-pre-wrap">{failure.message}</div>
            {retryable ? (
              <Button className="h-6 gap-1 px-2 text-[12px]" disabled={busy} onClick={retry} size="sm" variant="outline">
                <RotateCcw className="size-3" />
                Try again
              </Button>
            ) : null}
            <Button
              className="h-6 gap-1 px-2 text-[12px]"
              onClick={() => openSettings("agents")}
              size="sm"
              variant="outline"
            >
              <Settings2 className="size-3" />
              Open Settings › Agents
            </Button>
            <Button className="h-6 px-2 text-[12px]" onClick={() => setFailure(null)} size="sm" variant="outline">
              Dismiss
            </Button>
          </div>
        ) : listError ? (
          // Keyed apart: the two cards sit in the same place, and one card for both would carry a
          // failed read's "Tried again" count over to the sign-in card a good read turns it into.
          <div className="mt-4" key="list-error">
            <AgentSetupCard
              agents={[]}
              message={`text-to-cad could not read which agents are on this machine: ${listError}`}
              onRetry={reloadAgents}
              title="Could not check for agents"
            />
          </div>
        ) : noAgent ? (
          <div className="mt-4" key="no-agent">
            <AgentSetupCard
              agents={offered}
              message={`Sign in to ${signInTo}, or install one. text-to-cad runs a coding agent you already use.`}
              title="No agent ready"
            />
          </div>
        ) : null}

        {checking ? (
          <p className="mt-4 text-center text-[13px] text-muted-foreground" role="status">
            Still checking which agents are installed…
          </p>
        ) : null}

        <div className="mt-5">
          {context}
          <Composer
            autoFocus
            chips={chips}
            commands={[]}
            disabled={busy}
            onSubmit={submitFromComposer}
            refuseSend={unavailable}
            // A CAD hint, on this screen only: the live session's box stays
            // "Do anything" — by then the person knows what it is for.
            placeholder={busy && agent ? `Starting ${agent.name}…` : "Describe a part to build…"}
            newDraftKey={draftKey}
            sessionId={null}
            status={busy ? "submitted" : "ready"}
            trailing={trailing}
          />
        </div>
      </div>
    </div>
  );
}

/** Resolves once detection has answered (`ready`), at once when it already has. */
function agentsReady(): Promise<void> {
  if (useAgents.getState().ready) return Promise.resolve();
  return new Promise((resolve) => {
    const unsubscribe = useAgents.subscribe((state) => {
      if (!state.ready) return;
      unsubscribe();
      resolve();
    });
  });
}

/** The agent a send would start with, from the table: the default if installed, else the first. */
function firstAgentId(agents: AgentStatus[], defaultId: string | null): string | null {
  const installedNow = agents.filter((candidate) => candidate.installed || candidate.launchWithoutBinary);
  if (defaultId && installedNow.some((candidate) => candidate.id === defaultId)) return defaultId;
  return (installedNow.find((candidate) => candidate.auth !== "unauthenticated") ?? installedNow[0])?.id ?? null;
}

/** Whether the box still holds exactly the draft a failed start put back into it. */
function unchangedSince(attempt: TakenDraft, key: string): boolean {
  const state = useComposer.getState();
  const annotations = state.annotations[key] ?? [];
  return (state.drafts[key] ?? "") === attempt.text
    && annotations.length === attempt.annotations.length
    && annotations.every((annotation, index) =>
      annotation.id === attempt.annotations[index]?.id && annotation.text === attempt.annotations[index]?.text);
}

/** A mode or effort chip's place while detection and the probes are out. */
function ChipSkeleton({ slot, width }: { slot: "mode" | "effort"; width: string }) {
  return (
    <span aria-hidden className={`inline-flex h-7 shrink-0 items-center px-1.5 ${width}`} data-chip={`${slot}-loading`}>
      <span className="h-3.5 w-full animate-pulse rounded bg-muted" />
    </span>
  );
}

/** The model chip's place while the installed agents' probes are out. */
function ModelsLoading() {
  return (
    <button
      className="inline-flex h-7 w-[132px] shrink-0 cursor-default items-center gap-1.5 rounded-md px-1.5 text-[12px] leading-none text-muted-foreground"
      data-chip="model-loading"
      disabled
      type="button"
    >
      <Loader2 className="size-3.5 animate-spin" />
      Loading models…
    </button>
  );
}

function Dot() {
  return (
    <span aria-hidden className="text-[12px] text-muted-foreground/60">
      ·
    </span>
  );
}
