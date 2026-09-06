import { useState } from "react";
import { AlertCircle } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { resolveGitMode, useProjectGitInfo } from "@renderer/lib/git-mode";
import { useAcp } from "@renderer/state/acp";
import { useAgents, useInstalledAgents } from "@renderer/state/agents";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import type { ApprovalMode, PromptBlock } from "@shared/acp/types";
import type { GitMode, Project } from "@shared/types";

import { AuthPrompt } from "./AuthPrompt";
import { Composer } from "./Composer";
import { AgentChip, ApprovalChip, GitModeChip, ProjectChip } from "./ComposerChips";
import { errorMessage, isAuthError } from "./view";

/**
 * The new-session state (plan §2): "What should we build in <project>?",
 * a line saying what a session is, the context strip — project · git mode ·
 * agent, Codex's — and an empty composer with its approval chip. Nothing
 * else: a grid of canned prompts under the box is four guesses at what
 * somebody came here to do. Sending creates the session — `sessions.create`
 * spawns the agent — selects it, and sends the first prompt; the transcript
 * takes over from there.
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
  const agent = agents.find((candidate) => candidate.id === resolvedAgentId) ?? null;

  const chooseAgent = (id: string) => {
    setAgentId(id);
    setFailure(null);
  };

  const start = async (text: string, content: PromptBlock[]) => {
    if (!resolvedAgentId) {
      setFailure({ message: "Install an agent first — Settings › Agents lists what Hardcore can run.", auth: false });
      return;
    }
    setBusy(true);
    setFailure(null);
    let sessionId: string;
    try {
      sessionId = await create({
        projectId: project.id,
        agentId: resolvedAgentId,
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
  // it treats git, who runs it. Each is a menu; none of them changes once the
  // session exists, which is why they are not in the composer's row.
  const context = (
    <div className="mb-1.5 flex items-center gap-1 px-1" data-context-strip>
      <ProjectChip onChange={setActiveProject} project={project} />
      <Dot />
      <GitModeChip gitMode={resolvedGitMode} info={gitInfo} onChange={setGitMode} />
      <Dot />
      <AgentChip agentId={resolvedAgentId} onChange={chooseAgent} />
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
