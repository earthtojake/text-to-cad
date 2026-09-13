import { ChevronsDown, RotateCw } from 'lucide-react';
import { Button } from '../../primitives/button';
import { Checkbox } from '../../primitives/checkbox';
import { Combobox } from '../../primitives/combobox/combobox';
import { Input } from '../../primitives/input';
import { Spinner } from '../../primitives/spinner';
import { Tabs } from '../../primitives/tabs/tabs';
import type {
  CreateTaskBranchOption,
  CreateTaskExistingWorkspaceOption,
  CreateTaskModalProps,
  CreateTaskReadyWorkspaceDetail,
  CreateTaskSearchChoice,
  CreateTaskSetupPreview,
  CreateTaskWorkspaceState,
} from './create-task-modal.types';
import type { CreateTaskOptionLike } from './create-task-options';
import {
  CreateTaskOptionState,
  availabilityReason,
  optionsFrom,
  selectedOption,
} from './create-task-options';
import * as styles from './create-task-modal.css';

function SetupPreview({
  setup,
  onIntent,
}: {
  setup: CreateTaskSetupPreview;
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  return (
    <div className={styles.field}>
      <Button
        size="xs"
        onClick={() =>
          onIntent({ type: 'workspace.setup-expanded-changed', expanded: !setup.expanded })
        }
      >
        Setup steps ({setup.steps.length})
        <ChevronsDown />
      </Button>
      {setup.expanded && (
        <ol className={styles.setupList}>
          {setup.steps.map((step) => (
            <li key={step.id}>
              {step.label}
              {step.description ? ` — ${step.description}` : ''}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function SearchChoiceSelect<T extends CreateTaskOptionLike>({
  label,
  choice,
  open,
  getLabel,
  onSelect,
  onQueryChange,
  onRetry,
  onOpenChange,
}: {
  label: string;
  choice: CreateTaskSearchChoice<T>;
  open?: boolean;
  getLabel: (option: T) => string;
  onSelect: (id: string) => void;
  onQueryChange: (query: string) => void;
  onRetry: () => void;
  onOpenChange?: (open: boolean) => void;
}) {
  const unavailable = availabilityReason(choice.availability);
  const selected = selectedOption(choice.selection);
  const items = [...optionsFrom(choice.options)];
  return (
    <div className={styles.field}>
      <span className={styles.fieldLabel}>{label}</span>
      <Combobox.Root
        items={items}
        value={selected}
        open={open}
        disabled={Boolean(unavailable)}
        inputValue={choice.query}
        onOpenChange={(nextOpen) => onOpenChange?.(nextOpen)}
        onInputValueChange={(query) => onQueryChange(query)}
        onValueChange={(option: T | null) => {
          if (option && !unavailable) onSelect(option.id);
        }}
        isItemEqualToValue={(left: T, right: T) => left.id === right.id}
        filter={() => true}
      >
        <Combobox.Input
          showTrigger
          disabled={Boolean(unavailable)}
          aria-label={`Search ${label}`}
          placeholder={`Search ${label}…`}
          title={unavailable}
        />
        <Combobox.Content width="content-at-least-trigger">
          <CreateTaskOptionState state={choice.options} onRetry={onRetry} />
          {items.length > 0 && (
            <Combobox.List>
              {items.map((option) => (
                <Combobox.Item
                  key={option.id}
                  value={option}
                  disabled={option.availability.kind === 'unavailable'}
                  title={availabilityReason(option.availability)}
                >
                  {getLabel(option)}
                </Combobox.Item>
              ))}
            </Combobox.List>
          )}
        </Combobox.Content>
      </Combobox.Root>
    </div>
  );
}

export function WorkspaceSettingsDetail({
  workspace,
  nested,
  onIntent,
}: {
  workspace: Extract<CreateTaskWorkspaceState, { kind: 'inspectable' }>;
  nested: 'none' | 'source-branch' | 'existing-workspace';
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  if (workspace.detail.kind === 'resolving') {
    return (
      <div className={styles.state} aria-busy="true">
        <Spinner />
        Resolving Workspace…
      </div>
    );
  }
  if (workspace.detail.kind === 'error') {
    return (
      <div className={styles.state} role="alert">
        {workspace.detail.message}
        {workspace.detail.retryable && (
          <Button
            size="sm"
            onClick={() => onIntent({ type: 'workspace.retry-requested', target: 'detail' })}
          >
            Retry
          </Button>
        )}
      </div>
    );
  }
  if (workspace.detail.kind === 'unavailable') {
    return (
      <div className={styles.state}>
        <span>{workspace.detail.reason}</span>
        {workspace.detail.recoverable && (
          <Button
            size="sm"
            onClick={() => onIntent({ type: 'workspace.retry-requested', target: 'detail' })}
          >
            <RotateCw />
            Retry
          </Button>
        )}
      </div>
    );
  }
  const detail = workspace.detail.detail;
  if (detail.preset === 'repo-root') {
    return (
      <div className={styles.detailStack}>
        <strong>Repository directory</strong>
        <span>{detail.repositoryPath}</span>
        <p className={styles.notice}>{detail.consequence}</p>
      </div>
    );
  }
  if (detail.preset === 'use-existing') {
    return (
      <div className={styles.detailStack}>
        <SearchChoiceSelect
          label="Workspace"
          choice={detail.workspace}
          open={nested === 'existing-workspace'}
          getLabel={(workspaceOption: CreateTaskExistingWorkspaceOption) =>
            `${workspaceOption.label} · ${workspaceOption.path}`
          }
          onOpenChange={(nextOpen) =>
            onIntent({
              type: 'overlay.changed',
              overlay: {
                kind: 'workspace-settings',
                nested: nextOpen ? 'existing-workspace' : 'none',
              },
            })
          }
          onQueryChange={(query) => onIntent({ type: 'workspace.existing-query-changed', query })}
          onRetry={() =>
            onIntent({ type: 'workspace.retry-requested', target: 'existing-workspaces' })
          }
          onSelect={(workspaceId) => onIntent({ type: 'workspace.existing-selected', workspaceId })}
        />
      </div>
    );
  }
  if (detail.preset === 'checkout-pr') {
    return (
      <div className={styles.detailStack}>
        <strong>
          #{detail.pullRequest.number} · {detail.pullRequest.title}
        </strong>
        <span className={styles.itemDescription}>{detail.pullRequest.headBranch}</span>
        <SetupPreview setup={detail.setup} onIntent={onIntent} />
      </div>
    );
  }
  if (detail.preset === 'pr-new-branch') {
    return (
      <div className={styles.detailStack}>
        <strong>
          #{detail.pullRequest.number} · {detail.pullRequest.title}
        </strong>
        <BranchNameField branchName={detail.branchName} onIntent={onIntent} />
        <PushBranchField pushBranch={detail.pushBranch} onIntent={onIntent} />
        <SetupPreview setup={detail.setup} onIntent={onIntent} />
      </div>
    );
  }
  return (
    <div className={styles.detailStack}>
      <Tabs.Root
        value={detail.mode}
        onValueChange={(mode) => {
          if (mode === 'checkout' || mode === 'create') {
            onIntent({ type: 'workspace.worktree-mode-changed', mode });
          }
        }}
      >
        <Tabs.List aria-label="New worktree mode">
          <Tabs.Tab value="checkout">Checkout branch</Tabs.Tab>
          <Tabs.Tab value="create">Create new branch</Tabs.Tab>
        </Tabs.List>
      </Tabs.Root>
      <SearchChoiceSelect
        label="Source branch"
        choice={detail.sourceBranch}
        open={nested === 'source-branch'}
        getLabel={(branch: CreateTaskBranchOption) => branch.label}
        onOpenChange={(nextOpen) =>
          onIntent({
            type: 'overlay.changed',
            overlay: {
              kind: 'workspace-settings',
              nested: nextOpen ? 'source-branch' : 'none',
            },
          })
        }
        onQueryChange={(query) =>
          onIntent({ type: 'workspace.source-branch-query-changed', query })
        }
        onRetry={() => onIntent({ type: 'workspace.retry-requested', target: 'source-branches' })}
        onSelect={(branchId) => onIntent({ type: 'workspace.source-branch-selected', branchId })}
      />
      {detail.mode === 'checkout' && detail.conflict.kind === 'branch-in-use' && (
        <div className={styles.notice}>
          <span>{detail.conflict.message}</span>
          <Button
            size="xs"
            onClick={() => {
              const workspaceId =
                detail.conflict.kind === 'branch-in-use' ? detail.conflict.workspace.id : null;
              if (workspaceId)
                onIntent({
                  type: 'workspace.reuse-conflict-requested',
                  workspaceId,
                });
            }}
          >
            Reuse existing Workspace
          </Button>
        </div>
      )}
      {detail.mode === 'create' && (
        <>
          <BranchNameField branchName={detail.branchName} onIntent={onIntent} />
          <PushBranchField pushBranch={detail.pushBranch} onIntent={onIntent} />
        </>
      )}
      <SetupPreview setup={detail.setup} onIntent={onIntent} />
    </div>
  );
}

function BranchNameField({
  branchName,
  onIntent,
}: {
  branchName: Extract<CreateTaskReadyWorkspaceDetail, { preset: 'pr-new-branch' }>['branchName'];
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  return (
    <label className={styles.field}>
      <span className={styles.fieldLabel}>Branch name</span>
      <span className={styles.inline}>
        <Input
          value={branchName.value}
          aria-invalid={branchName.validation.kind === 'invalid'}
          onChange={(event) =>
            onIntent({ type: 'workspace.branch-name-changed', value: event.target.value })
          }
        />
        {branchName.source === 'override' && (
          <Button
            size="xs"
            onClick={() => onIntent({ type: 'workspace.branch-name-reset-requested' })}
          >
            Reset
          </Button>
        )}
      </span>
      {branchName.validation.kind === 'invalid' && (
        <span className={styles.error}>{branchName.validation.message}</span>
      )}
    </label>
  );
}

function PushBranchField({
  pushBranch,
  onIntent,
}: {
  pushBranch: Extract<CreateTaskReadyWorkspaceDetail, { preset: 'pr-new-branch' }>['pushBranch'];
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  return (
    <label className={styles.inline}>
      <Checkbox
        checked={pushBranch.kind === 'supported' ? pushBranch.value : false}
        aria-disabled={pushBranch.kind === 'unsupported' ? true : undefined}
        onCheckedChange={(value) => {
          if (pushBranch.kind === 'supported') {
            onIntent({ type: 'workspace.push-branch-changed', value });
          }
        }}
      />
      Push branch after creation
      {pushBranch.kind === 'unsupported' && (
        <span className={styles.itemDescription}>{pushBranch.reason}</span>
      )}
    </label>
  );
}
