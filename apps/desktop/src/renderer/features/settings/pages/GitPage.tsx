/**
 * Git and worktrees (plan §9): where a session's working directory comes from,
 * and what text-to-cad is allowed to create and remove around it.
 *
 * The rows above the fold are settings — read by `projects/workspace.ts` when
 * a session is created, by the sweep after each worktree is made, and by the
 * review's commit popover. Below them is Codex's per-project section: one card
 * per project listing the worktrees that exist right now, with the two actions
 * that make sense on one.
 */
import { useEffect, useId, useState } from "react";
import { Folder, TriangleAlert } from "lucide-react";
import { Spinner } from "@renderer/components/ui/spinner";
import { Alert, AlertDescription } from "@text-to-cad/ui/primitives/alert";

import { Button } from "@renderer/components/ui/button";
import { Textarea } from "@renderer/components/ui/textarea";
import {
  PathRow,
  SelectRow,
  SettingCard,
  SettingRow,
  SwitchRow,
  TextRow,
  useDraft,
} from "@renderer/features/settings/SettingCard";
import {
  useSettingsFallbacks,
  useSettingsPatch,
  useSettingsValue,
} from "@renderer/features/settings/settings-value";
import { ensureWorktrees, useWorktreeCache } from "@renderer/features/settings/worktree-cache";
import { runUiCommand } from "@renderer/state/bridge";
import { useProjects } from "@renderer/state/projects";
import type { Worktree } from "@shared/ipc/git";
import { branchPrefixProblem, defaultSettings, type GitMode, type Project } from "@shared/types";
import { errorMessage } from "@shared/ipc/errors";
import { basename } from "@renderer/lib/paths";

/**
 * The two choices the composer offers (`lib/git-mode.ts`). `none` is not one
 * of them: it is what "Local" means in a folder that is not a repository, and
 * that is decided per project when the session is created, not here.
 */
const GIT_MODES: { value: GitMode; label: string }[] = [
  { value: "checkout", label: "Local" },
  { value: "worktree", label: "New worktree" },
];

const KEEP_PRESETS = [3, 5, 10, 20, 50];

/** What a stored prefix git refuses is replaced with by "Use default": the schema's own. */
const DEFAULT_BRANCH_PREFIX = defaultSettings().branchPrefix;

/**
 * The presets, plus the stored limit when it is none of them (the schema
 * takes any count from 1): a select whose value matches no option draws
 * blank, which reads as "no limit" when there is one.
 */
function keepLimits(stored: number) {
  const counts = KEEP_PRESETS.includes(stored) ? KEEP_PRESETS : [...KEEP_PRESETS, stored].sort((a, b) => a - b);
  return counts.map((count) => ({ value: String(count), label: `Keep ${count}` }));
}

export function GitPage() {
  const settings = useSettingsValue();
  const patch = useSettingsPatch();
  // A prefix stored before git's rules were checked, which main reads as the
  // default (`settings.fallbacks`): asked again whenever settings change, so
  // the note goes once a prefix is set.
  const fallbacks = useSettingsFallbacks();
  const storedPrefix = fallbacks.refused.branchPrefix ?? null;

  return (
    <>
      <SettingCard title="New sessions">
        <SelectRow
          description="Where a new session works: the project's own folder, or a worktree of its own. Every session can override it."
          keywords="branch checkout worktree directory local"
          onChange={(defaultGitMode) => patch({ defaultGitMode })}
          options={GIT_MODES}
          title="Default git mode"
          // A folder that is not a repository resolves Local to `none` when
          // the session is made; the setting itself only names the choice.
          value={settings.defaultGitMode === "worktree" ? "worktree" : "checkout"}
        />
        <TextRow
          description="Prepended to every branch text-to-cad creates."
          keywords="branch name namespace"
          onChange={(branchPrefix) => patch({ branchPrefix })}
          placeholder="text-to-cad/"
          // Not the muted note a description is: the stored value is wrong,
          // and it says so in the kit's warning tone (its Alert's `warning`
          // variant), boxed, beside a value typed here and refused, which is
          // a line of red text.
          warning={
            storedPrefix === null ? undefined : (
              <Alert className="mt-1 px-3 py-2 text-xs" data-stored-prefix variant="warning">
                <TriangleAlert />
                <AlertDescription className="text-xs text-foreground">
                  {`The stored prefix “${storedPrefix}” is not one git accepts, so “${settings.branchPrefix}” is used until another is set. ${branchPrefixProblem(storedPrefix) ?? ""}`.trim()}
                  {/* The field already shows the default, so typing it again
                      changes nothing the row would write: this is the one way
                      to store it over the bad one. */}
                  <Button
                    className="h-6 px-2 text-[12px]"
                    onClick={() => patch({ branchPrefix: DEFAULT_BRANCH_PREFIX })}
                    size="sm"
                    variant="outline"
                  >
                    Use default
                  </Button>
                </AlertDescription>
              </Alert>
            )
          }
          problem={branchPrefixProblem}
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
            void window.textToCad.dialogs
              .chooseDirectory({
                title: "Worktree root",
                defaultPath: settings.worktreeRoot ?? undefined,
              })
              .then((chosen) => chosen && patch({ worktreeRoot: chosen.path }));
          }}
          note={
            fallbacks.gone.worktreeRoot?.reason === "file"
              ? "This is a file, not a folder, so worktrees cannot be made here."
              : fallbacks.gone.worktreeRoot
                ? "This folder no longer exists; it is created again with the next worktree."
                : undefined
          }
          onClear={() => patch({ worktreeRoot: null })}
          placeholder="~/.text-to-cad/worktrees"
          title="Worktree root"
          value={settings.worktreeRoot}
        />
        <SwitchRow
          checked={settings.fetchBeforeCreate}
          description="Fetch the remote before branching, and start a new worktree from the current branch's upstream (or the default branch when it has none). Without a connection it starts from where the checkout is."
          keywords="pull remote origin"
          onChange={(fetchBeforeCreate) => patch({ fetchBeforeCreate })}
          title="Fetch before creating"
        />
        <SwitchRow
          checked={settings.autoDeleteWorktrees}
          description="After a new worktree is created, remove the oldest idle ones beyond the limit below. Only worktrees text-to-cad created, and never one that is in use, locked or holds uncommitted work."
          keywords="prune clean remove old"
          onChange={(autoDeleteWorktrees) => patch({ autoDeleteWorktrees })}
          title="Auto-delete old worktrees"
        />
        <SelectRow
          description={
            settings.autoDeleteWorktrees
              ? "How many idle worktrees per project the sweep keeps. In-use and locked ones are not counted; one with unsaved work is counted, then kept."
              : "How many idle worktrees per project the sweep keeps. Nothing is swept while Auto-delete old worktrees is off."
          }
          disabled={!settings.autoDeleteWorktrees}
          keywords="limit count retain"
          onChange={(value) => patch({ worktreeKeepLimit: Number(value) })}
          options={keepLimits(settings.worktreeKeepLimit)}
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
 * Only text-to-cad's own: a worktree the person made themselves, somewhere else,
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
  const cardId = useId();
  const worktrees = useWorktreeCache((state) => state.lists[project.id]) ?? null;
  const epoch = useWorktreeCache((state) => state.epoch);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A mount reads afresh over the list the visit already has (`worktree-cache.ts`);
  // `epoch` reads again after an invalidation.
  useEffect(() => {
    void ensureWorktrees(project.id, { fresh: true });
  }, [project.id]);
  useEffect(() => {
    void ensureWorktrees(project.id);
  }, [project.id, epoch]);

  const remove = async (worktree: Worktree) => {
    setBusy(worktree.path);
    setError(null);
    try {
      await window.textToCad.git.removeWorktree({ projectId: project.id, path: worktree.path });
      useWorktreeCache.getState().invalidate();
    } catch (caught) {
      setError(errorMessage(caught));
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
      {worktrees.map((worktree, index) => {
        const kept = keptBecause(worktree);
        const keptId = `${cardId}-kept-${index}`;
        return (
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
                  New session in this worktree
                </Button>
                <Button
                  className="h-8"
                  // A worktree with uncommitted work, a lock, or a thread still
                  // open on it, is not deleted from here: main refuses the
                  // first, git the second, and the third would pull the
                  // directory out from under a running agent.
                  //
                  // A disabled button takes no hover and no hint, so the reason
                  // is its accessible description rather than a native title
                  // nobody with a keyboard or a screen reader would ever get.
                  aria-describedby={kept ? keptId : undefined}
                  disabled={busy === worktree.path || kept !== null}
                  onClick={() => void remove(worktree)}
                  size="sm"
                  variant="ghost"
                >
                  {busy === worktree.path ? <Spinner aria-hidden className="size-3.5" /> : null}
                  Delete
                </Button>
                {kept ? (
                  <span className="sr-only" id={keptId}>
                    {kept}
                  </span>
                ) : null}
              </div>
            }
            description={describe(worktree)}
            key={worktree.path}
            keywords={`worktree branch ${project.name} ${worktree.branch ?? ""}`}
            title={worktree.branch ?? basename(worktree.path)}
          />
        );
      })}
      {error ? (
        <p className="px-4 py-2 text-[12px] text-destructive">{error}</p>
      ) : null}
      <SettingRow
        control={
          <Button
            className="h-8 gap-1.5"
            onClick={() => {
              void window.textToCad.shell.showItemInFolder({ projectId: project.id, worktrees: true });
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

/** Why a worktree's Delete is off, or null when it is not. */
function keptBecause(worktree: Worktree): string | null {
  if (worktree.locked) {
    return "This worktree is locked (git worktree lock), so it is kept until it is unlocked.";
  }
  if (worktree.dirty === null) {
    return "Git could not check this worktree for uncommitted changes or ignored files, so it is kept.";
  }
  if (worktree.dirty) {
    return "This worktree has uncommitted changes or ignored files (like .env) that deleting it would lose.";
  }
  if (worktree.openSessions > 0) {
    return "A session is still open in this worktree.";
  }
  return null;
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
      `${worktree.openSessions} open session${worktree.openSessions === 1 ? "" : "s"} (in use)`,
    );
  }
  if (worktree.locked) {
    parts.push("locked");
  }
  if (worktree.dirty) {
    parts.push("uncommitted or ignored files");
  } else if (worktree.dirty === null) {
    parts.push("could not check for unsaved files");
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

/**
 * A row whose control is a paragraph, so it sits under the title rather than
 * beside it. Committed on blur, not per keystroke (`useDraft`): Enter is a
 * newline here.
 */
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
  const draft = useDraft(value, onChange);
  return (
    <SettingRow description={description} keywords={keywords} title={title}>
      <Textarea
        aria-label={title}
        className="min-h-20 text-sm"
        onBlur={draft.onBlur}
        onChange={(event) => draft.onChange(event.target.value)}
        onFocus={draft.onFocus}
        placeholder={placeholder}
        value={draft.value}
      />
    </SettingRow>
  );
}
