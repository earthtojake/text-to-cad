/**
 * Git & Worktrees (plan §9): where a session's working directory comes from,
 * and what Hardcore is allowed to create and remove around it.
 *
 * The rows above the fold are settings — read by `projects/workspace.ts` when
 * a session is created, by the sweep after each worktree is made, and by the
 * review's commit popover. Below them is Codex's per-project section: one card
 * per project listing the worktrees that exist right now, with the two actions
 * that make sense on one.
 */
import { useCallback, useEffect, useState } from "react";
import { Folder, Loader2 } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { Textarea } from "@renderer/components/ui/textarea";
import {
  PathRow,
  SelectRow,
  SettingCard,
  SettingRow,
  SwitchRow,
  TextRow,
} from "@renderer/features/settings/SettingCard";
import {
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { runUiCommand } from "@renderer/state/bridge";
import { useProjects } from "@renderer/state/projects";
import type { Worktree } from "@shared/ipc/git";
import type { GitMode, Project } from "@shared/types";

const GIT_MODES: { value: GitMode; label: string }[] = [
  { value: "none", label: "Plain directory" },
  { value: "checkout", label: "Current branch" },
  { value: "worktree", label: "New worktree" },
];

const KEEP_LIMITS = [3, 5, 10, 20, 50].map((count) => ({
  value: String(count),
  label: `Keep ${count}`,
}));

export function GitPage() {
  const settings = useSettingsValue();
  const patch = useSettingsPatch();

  return (
    <>
      <SettingCard title="New sessions">
        <SelectRow
          description="What a new session's working directory is. Every session can override it."
          keywords="branch checkout worktree directory"
          onChange={(defaultGitMode) => patch({ defaultGitMode })}
          options={GIT_MODES}
          title="Default git mode"
          value={settings.defaultGitMode}
        />
        <TextRow
          description="Prepended to every branch Hardcore creates."
          keywords="branch name namespace"
          onChange={(branchPrefix) => patch({ branchPrefix })}
          placeholder="hardcore/"
          title="Branch prefix"
          value={settings.branchPrefix}
          width="w-[200px]"
        />
      </SettingCard>

      <SettingCard title="Worktrees">
        <PathRow
          description="Every worktree lives here, under a folder per project, whichever agent made it."
          keywords="directory location root"
          onChoose={() => {
            void window.hardcore.dialogs
              .chooseDirectory({
                title: "Worktree root",
                defaultPath: settings.worktreeRoot ?? undefined,
              })
              .then((chosen) => chosen && patch({ worktreeRoot: chosen.path }));
          }}
          onClear={() => patch({ worktreeRoot: null })}
          placeholder="~/.hardcore/worktrees"
          title="Worktree root"
          value={settings.worktreeRoot}
        />
        <SwitchRow
          checked={settings.fetchBeforeCreate}
          description="Fetch the remote before branching, so a new worktree starts from what is on the server."
          keywords="pull remote origin"
          onChange={(fetchBeforeCreate) => patch({ fetchBeforeCreate })}
          title="Fetch before creating"
        />
        <SwitchRow
          checked={settings.autoDeleteWorktrees}
          description="Remove the oldest worktrees once there are more than the limit below. Only ones Hardcore created."
          keywords="prune clean remove old"
          onChange={(autoDeleteWorktrees) => patch({ autoDeleteWorktrees })}
          title="Auto-delete old worktrees"
        />
        <SelectRow
          description="How many worktrees per project survive the sweep."
          keywords="limit count retain"
          onChange={(value) => patch({ worktreeKeepLimit: Number(value) })}
          options={KEEP_LIMITS}
          title="Keep limit"
          value={String(settings.worktreeKeepLimit)}
          width="w-[140px]"
        />
      </SettingCard>

      <SettingCard title="Pull requests">
        <SwitchRow
          checked={settings.draftPullRequests}
          description="Open pull requests as drafts. Uses gh when it is installed."
          keywords="draft pr github"
          onChange={(draftPullRequests) => patch({ draftPullRequests })}
          title="Create draft pull requests"
        />
        <InstructionsRow
          description="Added to what the agent is told when it commits. House style, trailers, ticket references."
          keywords="message convention trailer"
          onChange={(commitInstructions) => patch({ commitInstructions })}
          placeholder="Reference the issue in the body. Never mention the tool that wrote the change."
          title="Commit instructions"
          value={settings.commitInstructions}
        />
        <InstructionsRow
          description="Added to what the agent is told when it opens a pull request."
          keywords="description template review"
          onChange={(pullRequestInstructions) => patch({ pullRequestInstructions })}
          placeholder="Summary, then a Testing section. Link the design doc."
          title="Pull request instructions"
          value={settings.pullRequestInstructions}
        />
      </SettingCard>

      <ProjectWorktrees />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Per-project worktrees                                                       */
/* -------------------------------------------------------------------------- */

/**
 * A card per project, listing the worktrees under this project's worktree
 * directory (Codex's Worktrees page, plan §2).
 *
 * Only Hardcore's own: a worktree the person made themselves, somewhere else,
 * is theirs, and a Delete button beside it would be the app offering to remove
 * something it never created. A project with none is skipped rather than shown
 * empty — a settings page that lists every project you have ever added, each
 * saying "no worktrees", is a page nobody reads to the bottom of.
 */
function ProjectWorktrees() {
  const projects = useProjects((state) => state.projects);

  if (projects.length === 0) {
    return null;
  }
  return (
    <>
      {projects.map((project) => (
        <ProjectWorktreeCard key={project.id} project={project} />
      ))}
    </>
  );
}

function ProjectWorktreeCard({ project }: { project: Project }) {
  const [worktrees, setWorktrees] = useState<Worktree[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const read = useCallback(() => {
    void window.hardcore.git
      .worktrees({ projectId: project.id })
      .then(setWorktrees)
      .catch(() => setWorktrees([]));
  }, [project.id]);

  useEffect(read, [read]);

  const remove = async (worktree: Worktree) => {
    setBusy(worktree.path);
    setError(null);
    try {
      await window.hardcore.git.removeWorktree({ projectId: project.id, path: worktree.path });
      read();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  // Nothing to say until the read comes back, and nothing to say afterwards
  // if the project has no worktrees of ours.
  if (!worktrees || worktrees.length === 0) {
    return null;
  }

  return (
    <SettingCard title={`Worktrees · ${project.name}`}>
      {worktrees.map((worktree) => (
        <SettingRow
          control={
            <div className="flex items-center gap-1.5">
              <Button
                className="h-8"
                onClick={() =>
                  runUiCommand({
                    command: "new-session",
                    projectId: project.id,
                    cwd: worktree.path,
                  })
                }
                size="sm"
                variant="secondary"
              >
                New chat in this worktree
              </Button>
              <Button
                className="h-8"
                // A worktree with uncommitted work, or with a thread still
                // open on it, is not deleted from here: main refuses the
                // first, and the second would pull the directory out from
                // under a running agent.
                disabled={busy === worktree.path || worktree.dirty || worktree.openSessions > 0}
                onClick={() => void remove(worktree)}
                size="sm"
                title={
                  worktree.dirty
                    ? "This worktree has uncommitted changes"
                    : worktree.openSessions > 0
                      ? "A session is still open in this worktree"
                      : undefined
                }
                variant="ghost"
              >
                {busy === worktree.path ? <Loader2 className="size-3.5 animate-spin" /> : null}
                Delete
              </Button>
            </div>
          }
          description={describe(worktree)}
          key={worktree.path}
          keywords={`worktree branch ${project.name} ${worktree.branch ?? ""}`}
          title={worktree.branch ?? (worktree.path.split("/").pop() ?? worktree.path)}
        />
      ))}
      {error ? (
        <p className="px-4 py-2 text-[12px] text-destructive">{error}</p>
      ) : null}
      <SettingRow
        control={
          <Button
            className="h-8 gap-1.5"
            onClick={() => {
              void window.hardcore.shell.showItemInFolder({ path: parentOf(worktrees) });
            }}
            size="sm"
            variant="ghost"
          >
            <Folder className="size-3.5" />
            Reveal
          </Button>
        }
        description={parentOf(worktrees)}
        keywords="reveal finder folder directory"
        title="Where they live"
      />
    </SettingCard>
  );
}

/** The directory the project's worktrees sit in — `<worktree root>/<project>`. */
function parentOf(worktrees: Worktree[]): string {
  const first = worktrees[0]?.path ?? "";
  return first.slice(0, Math.max(0, first.lastIndexOf("/"))) || first;
}

/**
 * The one-line description under a worktree's branch: the folder's own name,
 * how long ago it was written in, and anything that stops it being deleted.
 *
 * The folder name and not the whole path: an absolute path is one unbreakable
 * word, so it cannot wrap, and it runs under the row's buttons instead. The
 * directory they share is printed once at the bottom of the card.
 */
function describe(worktree: Worktree): string {
  const parts = [worktree.path.split("/").pop() ?? worktree.path];
  if (worktree.lastUsedAt) {
    parts.push(`last used ${relative(worktree.lastUsedAt)}`);
  }
  if (worktree.openSessions > 0) {
    parts.push(
      `${worktree.openSessions} open session${worktree.openSessions === 1 ? "" : "s"}`,
    );
  }
  if (worktree.dirty) {
    parts.push("uncommitted changes");
  }
  return parts.join(" · ");
}

/** "4 minutes ago" — enough resolution to tell today's worktrees apart. */
function relative(at: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - at) / 1000));
  const units: [number, string][] = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [Number.POSITIVE_INFINITY, "week"],
  ];
  let value = seconds;
  for (const [size, name] of units) {
    if (value < size) {
      return `${Math.round(value)} ${name}${Math.round(value) === 1 ? "" : "s"} ago`;
    }
    value /= size;
  }
  return "a while ago";
}

/** A row whose control is a paragraph, so it sits under the title rather than beside it. */
function InstructionsRow({
  title,
  description,
  keywords,
  value,
  placeholder,
  onChange,
}: {
  title: string;
  description: string;
  keywords: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <SettingRow description={description} keywords={keywords} title={title}>
      <Textarea
        aria-label={title}
        className="min-h-20 text-sm"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </SettingRow>
  );
}
