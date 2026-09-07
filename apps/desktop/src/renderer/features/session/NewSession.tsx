import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { resolveGitMode, useProjectGitInfo } from "@renderer/lib/git-mode";
import { useAcp } from "@renderer/state/acp";
import { useAgentOptions, useProviderEffort, useProviderModels } from "@renderer/state/agent-options";
import { useAgents, useInstalledAgents } from "@renderer/state/agents";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import type { ApprovalMode, PromptBlock } from "@shared/acp/types";
import type { GitMode, Project } from "@shared/types";

import { AuthPrompt } from "./AuthPrompt";
import { Composer } from "./Composer";
import { ApprovalChip, EffortChip, GitModeChip, ModelChip, ProjectChip } from "./ComposerChips";
import { errorMessage, isAuthError } from "./view";

/**
 * The new-session state (plan §2): "What should we build in <project>?",
 * a line saying what a session is, the context strip — project · git mode ·
 * model · effort — and an empty composer with its approval chip. Nothing
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
 * Creation can fail before there is a session to show it in: the agent is
 * not signed in, or its adapter would not start. Those land here, above
 * the composer, with the agent's login as the action.
 */
export function NewSession({ project }: { project: Project }) {
  const settings = useSettings((state) => state.settings);
  const agents = useAgents((state) => state.agents);
  const installed = useInstalledAgents();
  const setActiveProject = useProjects((state) => state.setActive);
  const setActiveSession = useSessions((state) => state.setActive);
  const create = useAcp((state) => state.create);
  const setApproval = useAcp((state) => state.setApprovalMode);
  const submitPrompt = useComposer((state) => state.submit);
  const setDraft = useComposer((state) => state.setDraft);
  const probeOptions = useAgentOptions((state) => state.probe);
  const setAgentDefaults = useAgentOptions((state) => state.setDefaults);

  const [agentId, setAgentId] = useState<string | null>(null);
  const [gitMode, setGitMode] = useState<GitMode | null>(null);
  const [approval, setApprovalMode] = useState<ApprovalMode>("ask");
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
  const effort = useProviderEffort(pickedProvider?.agentId ?? null);
  // Who will actually run this: the model chip's provider, because that is
  // the choice the person made. Everything that names the agent — the
  // placeholder, the sign-in prompt when creation fails — names this one.
  const startingAgentId = pickedProvider?.agentId ?? resolvedAgentId;
  const agent = agents.find((candidate) => candidate.id === startingAgentId) ?? null;

  const chooseModel = (pickedAgentId: string, value: string) => {
    setAgentId(pickedAgentId);
    setFailure(null);
    void setAgentDefaults(pickedAgentId, { model: value });
  };

  const chooseEffort = (_configId: string, value: string) => {
    if (pickedProvider) {
      void setAgentDefaults(pickedProvider.agentId, { effort: value });
    }
  };

  const start = async (text: string, content: PromptBlock[]) => {
    if (!startingAgentId) {
      setFailure({ message: "Install an agent first — Settings › Agents lists what Hardcore can run.", auth: false });
      return;
    }
    setBusy(true);
    setFailure(null);
    let sessionId: string;
    try {
      // The model and the effort are not passed: they are this agent's stored
      // defaults, and main applies them to the session it just created — in
      // that order, because the model decides which efforts exist.
      sessionId = await create({
        projectId: project.id,
        agentId: startingAgentId,
        cwd: project.path,
        gitMode: resolvedGitMode,
      });
    } catch (error) {
      const message = errorMessage(error);
      // Main has already dropped the row: nothing to resume, nothing to list.
      setFailure({ message, auth: isAuthError(message) || agent?.auth === "unauthenticated" });
      setDraft("__new__", text);
      setBusy(false);
      return;
    }
    if (approval !== "ask") {
      void setApproval(sessionId, approval);
    }
    setDraft("__new__", "");
    setActiveSession(sessionId);
    setBusy(false);
    void submitPrompt(sessionId, text, content);
  };

  // What the session will be, as a strip above the box: where it runs, how
  // it treats git, which model runs it and how hard it thinks. The first two
  // cannot change once the session exists, which is why they are not in the
  // composer's row; the last two are the same chips the live session has.
  const context = (
    <div className="mb-1.5 flex items-center gap-1 px-1" data-context-strip>
      <ProjectChip onChange={setActiveProject} project={project} />
      <Dot />
      <GitModeChip gitMode={resolvedGitMode} info={gitInfo} onChange={setGitMode} />
      {providers.length > 0 ? (
        <>
          <Dot />
          <ModelChip agentId={pickedProvider?.agentId ?? null} onChange={chooseModel} providers={providers} />
        </>
      ) : null}
      {effort ? (
        <>
          <Dot />
          <EffortChip effort={effort} onChange={chooseEffort} />
        </>
      ) : null}
    </div>
  );
  const chips = <ApprovalChip mode={approval} onChange={setApprovalMode} />;

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
            sessionId={null}
            status={busy ? "submitted" : "ready"}
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
