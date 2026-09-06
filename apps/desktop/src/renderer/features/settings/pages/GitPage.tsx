/**
 * Git & Worktrees (plan §9): where a session's working directory comes from,
 * and what Hardcore is allowed to create and remove around it.
 *
 * Every value here is stored so P7 can read it — this page does not run git,
 * and nothing on it takes effect until a session is created.
 */
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
import type { GitMode } from "@shared/types";

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
    </>
  );
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
