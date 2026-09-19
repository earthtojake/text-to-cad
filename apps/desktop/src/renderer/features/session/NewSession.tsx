import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { resolveGitMode, useProjectGitInfo } from "@renderer/lib/git-mode";
import { useAcp } from "@renderer/state/acp";
import {
  useAgentOptions,
  useProviderEffort,
  useProviderMode,
  useProviderModels,
} from "@renderer/state/agent-options";
import { useAgents, useInstalledAgents } from "@renderer/state/agents";
import { newSessionKey, useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import type { PromptBlock } from "@shared/acp/types";
import type { GitMode, Project } from "@shared/types";

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
 * the composer, with the agent's login as the action.
 */
export function NewSession({ project }: { project: Project }) {
  const draftKey = newSessionKey(project.id);
  const draftRoot = useComposer((state) => state.draftRoots[draftKey]);
  const settings = useSettings((state) => state.settings);
  const agents = useAgents((state) => state.agents);
  const installed = useInstalledAgents();
  const setActiveProject = useProjects((state) => state.setActive);
  const setActiveSession = useSessions((state) => state.setActive);
  const create = useAcp((state) => state.create);
  const submitPrompt = useComposer((state) => state.submit);
  const setDraft = useComposer((state) => state.setDraft);
  const probeOptions = useAgentOptions((state) => state.probe);
  const setAgentDefaults = useAgentOptions((state) => state.setDefaults);
  const setAgentEffort = useAgentOptions((state) => state.setEffort);

  const [agentId, setAgentId] = useState<string | null>(null);
  const [gitMode, setGitMode] = useState<GitMode | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ message: string; auth: boolean } | null>(null);

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
  const installedIds = installed.map((candidate) => candidate.id).join(",");
  useEffect(() => {
    for (const id of installedIds.split(",").filter(Boolean)) {
      void probeOptions(id, project.id);
    }
  }, [installedIds, project.id, probeOptions]);

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

  const start = async (text: string, content: PromptBlock[]) => {
    if (!startingAgentId) {
      setDraft(draftKey, text);
      setFailure({ message: "Install an agent first — Settings › Agents lists what Hardcore can run.", auth: false });
      return;
    }
    setBusy(true);
    setFailure(null);
    let sessionId: string;
    try {
      // The model, the effort and the mode are not passed: they are this
      // agent's stored defaults, and main applies them to the session it
      // just created — in that order, because the model decides which
      // efforts exist.
      sessionId = await create({
        projectId: project.id,
        agentId: startingAgentId,
        ...(draftRoot ? { cwd: draftRoot } : {}),
        gitMode: resolvedGitMode,
      });
    } catch (error) {
      const message = errorMessage(error);
      // Main has already dropped the row: nothing to resume, nothing to list.
      setFailure({ message, auth: isAuthError(message) || agent?.auth === "unauthenticated" });
      setDraft(draftKey, text);
      if (draftRoot) useComposer.getState().setDraftRoot(draftKey, draftRoot);
      setBusy(false);
      return;
    }
    setDraft(draftKey, "");
    setActiveSession(sessionId);
    setBusy(false);
    void submitPrompt(sessionId, text, content);
  };

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
        <span className="text-xs text-muted-foreground" title={draftRoot}>In {draftRoot.split(/[\\/]/).pop()}</span>
      ) : <GitModeChip gitMode={resolvedGitMode} info={gitInfo} onChange={setGitMode} />}
    </div>
  );
  const chips = mode ? (
    <ModeChip currentModeId={mode.currentModeId} modes={mode.modes} onChange={chooseMode} />
  ) : null;
  const trailing = (
    <>
      {providers.length > 0 ? (
        <ModelChip agentId={pickedProvider?.agentId ?? null} onChange={chooseModel} providers={providers} />
      ) : null}
      {effort ? <EffortChip effort={effort} onChange={chooseEffort} /> : null}
    </>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-6 pb-10" data-new-session>
      <div className="w-full max-w-[720px]">
        <h1 className="text-center text-[22px] leading-tight font-medium tracking-tight text-balance">
          What should we build in {project.name}?
        </h1>
        <p className="mt-2 text-center text-[13px] text-balance text-muted-foreground">
          Hardcore runs the agent in this folder, with cadgen and the CAD skills already loaded.
        </p>

        {failure?.auth ? (
          <div className="mt-4">
            <AuthPrompt agent={agent} message={failure.message} onRetry={() => setFailure(null)} />
          </div>
        ) : failure ? (
          <div
            className="mt-4 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] leading-5"
            role="alert"
          >
            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
            <div className="min-w-0 flex-1 whitespace-pre-wrap">{failure.message}</div>
            <Button className="h-6 px-2 text-[12px]" onClick={() => setFailure(null)} size="sm" variant="outline">
              Dismiss
            </Button>
          </div>
        ) : null}

        <div className="mt-5">
          {context}
          <Composer
            autoFocus
            chips={chips}
            commands={[]}
            disabled={busy}
            onSubmit={start}
            placeholder={busy && agent ? `Starting ${agent.name}…` : "Do anything"}
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

function Dot() {
  return (
    <span aria-hidden className="text-[12px] text-muted-foreground/60">
      ·
    </span>
  );
}
