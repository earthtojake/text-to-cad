import { Input, SplitButton, Textarea, toast } from '@emdash/ui/react/primitives';
import { CheckCircle, Loader2 } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import { getTaskGitCheckoutStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';
import { formatPushErrorDetail } from '@core/features/source-control/api/git-error-messages';
import { gitCheckoutStoreToken } from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import { formatErrorType } from '@core/features/tasks/api/browser/utils';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import {
  useTaskComposition,
  useWorkspace,
  useWorkspaceId,
} from '@core/features/workbench/api/browser/task-composition-context';
import { useOpenModal } from '@core/manifests/browser/modal-api';

type CommitPhase =
  | 'idle'
  | 'committing'
  | 'commit-only-done'
  | 'committed'
  | 'pushing'
  | 'pushed'
  | 'opening-pr';

interface CommitCardProps {
  autoStage?: boolean;
}

export const CommitCard = observer(function CommitCard({ autoStage = false }: CommitCardProps) {
  const { projectId, taskId } = useTaskViewContext();
  const workspaceId = useWorkspaceId();
  const taskView = useTaskComposition();
  const workspace = useWorkspace();
  const git = workspace.get(gitCheckoutStoreToken);
  const diffView = taskView.diffView;
  const changesView = diffView?.changesView ?? null;
  const hasPRs = changesView?.expandedSections.pullRequests ?? false;
  const [commitMessage, setCommitMessage] = useState('');
  const [description, setDescription] = useState('');
  const [phase, setPhase] = useState<CommitPhase>('idle');
  const fullMessage = description ? `${commitMessage}\n\n${description}` : commitMessage;
  const isInFlight = phase !== 'idle';

  const openCreatePrModal = useOpenModal('createPrModal');
  const repositoryUrl = getGitRepositoryStore(projectId)?.pullRequestRepositoryUrl ?? null;

  if (!diffView || !changesView) return null;

  const branchName = getTaskGitCheckoutStore(projectId, taskId)?.branchName;
  const hasOpenPr = taskView.prStore?.pullRequests.some((p) => p.status === 'open') ?? false;
  const canCreatePr = Boolean(repositoryUrl) && Boolean(branchName) && !hasOpenPr;

  const stageAllIfNeeded = async (): Promise<boolean> => {
    if (!autoStage) return true;
    changesView.suppressNextAutoExpand('staged');
    const result = await git.stageAllFiles();
    if (!result.success) {
      toast.error(`Failed to stage changes: ${formatErrorType(result.error)} `);
      setPhase('idle');
      return false;
    }
    return true;
  };

  const doCommit = async () => {
    setPhase('committing');
    if (!(await stageAllIfNeeded())) return;
    const result = await git.commit(fullMessage);
    if (!result.success) {
      toast.error(`Failed to commit changes: ${formatErrorType(result.error)} `);
      setPhase('idle');
      return;
    }
    setCommitMessage('');
    setDescription('');
    if (!autoStage) {
      changesView.setExpanded({ unstaged: true, staged: false, pullRequests: hasPRs });
    }
    setPhase('commit-only-done');
    setTimeout(() => setPhase('idle'), 3000);
  };

  const doCommitAndPush = async () => {
    setPhase('committing');
    if (!(await stageAllIfNeeded())) return;
    const commitResult = await git.commit(fullMessage);
    if (!commitResult.success) {
      toast.error(`Failed to commit changes: ${formatErrorType(commitResult.error)} `);
      setPhase('idle');
      return;
    }
    setCommitMessage('');
    setDescription('');
    if (!autoStage) {
      changesView.setExpanded({ unstaged: true, staged: false, pullRequests: hasPRs });
    }
    setPhase('committed');
    await new Promise((r) => setTimeout(r, 1000));
    setPhase('pushing');
    const pushResult = await git.push();
    if (!pushResult.success) {
      toast.error(`Failed to push: ${formatPushErrorDetail(pushResult.error)}`);
      setPhase('idle');
      return;
    }
    setPhase('pushed');
    setTimeout(() => setPhase('idle'), 3000);
  };

  const doCommitAndCreatePr = async () => {
    setPhase('committing');
    if (!(await stageAllIfNeeded())) return;
    const commitResult = await git.commit(fullMessage);
    if (!commitResult.success) {
      toast.error(`Failed to commit changes: ${formatErrorType(commitResult.error)} `);
      setPhase('idle');
      return;
    }
    setCommitMessage('');
    setDescription('');
    if (!autoStage) {
      changesView.setExpanded({ unstaged: true, staged: false, pullRequests: hasPRs });
    }
    setPhase('opening-pr');
    await new Promise((r) => setTimeout(r, 500));
    setPhase('idle');
    void openCreatePrModal({
      projectId,
      taskId,
      repositoryUrl: repositoryUrl ?? '',
      branchName: branchName ?? '',
      draft: false,
      workspaceId,
    });
  };

  const actions = [
    { id: 'commit', label: 'Commit', action: () => void doCommit() },
    { id: 'commit-push', label: 'Commit & Push', action: () => void doCommitAndPush() },
    ...(canCreatePr
      ? [
          {
            id: 'commit-pr',
            label: 'Commit & Create PR',
            action: () => void doCommitAndCreatePr(),
          },
        ]
      : []),
  ];

  const effectiveAction =
    diffView.effectiveCommitAction === 'commit-pr' && !canCreatePr
      ? 'commit-push'
      : diffView.effectiveCommitAction;

  return (
    <div className="mx-2 mb-2 flex shrink-0 flex-col items-center justify-between gap-2 rounded-xl border border-border bg-background-1 p-2">
      <Input
        placeholder="Commit message"
        className="w-full bg-background"
        value={commitMessage}
        onChange={(e) => setCommitMessage(e.target.value)}
        disabled={isInFlight}
      />
      <Textarea
        placeholder="Description"
        className="w-full bg-background"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        disabled={isInFlight}
      />
      {phase === 'idle' && (
        <SplitButton
          options={actions.map(({ id, label }) => ({ id, label }))}
          size="sm"
          fullWidth
          disabled={!commitMessage.trim()}
          selectedId={effectiveAction}
          onSelectedChange={(id) =>
            diffView.setCommitAction(id as 'commit' | 'commit-push' | 'commit-pr')
          }
          commitOnSelect={false}
          onAction={(id) => actions.find((a) => a.id === id)?.action()}
        />
      )}
      {phase === 'committing' && (
        <StatusRow icon={<Loader2 className="size-4 animate-spin" />} label="Committing…" />
      )}
      {phase === 'opening-pr' && (
        <StatusRow icon={<Loader2 className="size-4 animate-spin" />} label="Opening PR…" />
      )}
      {(phase === 'commit-only-done' || phase === 'committed') && (
        <StatusRow
          icon={<CheckCircle className="size-4 text-foreground-success" />}
          label="Committed"
        />
      )}
      {phase === 'pushing' && (
        <StatusRow icon={<Loader2 className="size-4 animate-spin" />} label="Pushing…" />
      )}
      {phase === 'pushed' && (
        <StatusRow
          icon={<CheckCircle className="size-4 text-foreground-success" />}
          label="Pushed"
        />
      )}
    </div>
  );
});

function StatusRow({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex w-full items-center justify-center gap-2 py-1 text-sm text-foreground-muted">
      {icon}
      <span>{label}</span>
    </div>
  );
}
