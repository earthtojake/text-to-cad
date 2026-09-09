import { ChevronDown, Settings2 } from 'lucide-react';
import type { RefObject } from 'react';
import { Button } from '../../primitives/button';
import { Popover } from '../../primitives/popover';
import { Tabs } from '../../primitives/tabs/tabs';
import type {
  CreateTaskModalProps,
  CreateTaskWorkspacePreset,
  CreateTaskWorkspaceState,
} from './create-task-modal.types';
import { availabilityReason } from './create-task-options';
import { WorkspaceSettingsDetail } from './workspace-settings-detail';
import * as styles from './create-task-modal.css';

const WORKSPACE_PRESETS: readonly {
  id: CreateTaskWorkspacePreset;
  label: string;
  shortLabel: string;
}[] = [
  { id: 'new-worktree', label: 'Create new worktree', shortLabel: 'New worktree' },
  { id: 'repo-root', label: 'Use the repository directory', shortLabel: 'Repository' },
  { id: 'use-existing', label: 'Reuse an existing Workspace', shortLabel: 'Existing' },
  { id: 'checkout-pr', label: 'Checkout PR in worktree', shortLabel: 'Checkout PR' },
  { id: 'pr-new-branch', label: 'Create a new branch from PR', shortLabel: 'Branch from PR' },
];

function workspaceLabel(workspace: CreateTaskWorkspaceState): string {
  if (workspace.kind === 'terminally-unavailable') return 'Workspace unavailable';
  return (
    WORKSPACE_PRESETS.find((preset) => preset.id === workspace.selectedPreset)?.shortLabel ??
    'Workspace Settings'
  );
}

function isWorkspacePreset(value: unknown): value is CreateTaskWorkspacePreset {
  return WORKSPACE_PRESETS.some((preset) => preset.id === value);
}

export function WorkspaceSettingsPicker({
  state,
  open,
  nested,
  triggerRef,
  onIntent,
}: {
  state: CreateTaskWorkspaceState;
  open: boolean;
  nested: 'none' | 'source-branch' | 'existing-workspace';
  triggerRef: RefObject<HTMLButtonElement | null>;
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  const unavailable = state.kind === 'terminally-unavailable' ? state.reason : undefined;
  return (
    <Popover.Root
      open={open}
      onOpenChange={(nextOpen) => {
        if (unavailable) return;
        onIntent({
          type: 'overlay.changed',
          overlay: nextOpen ? { kind: 'workspace-settings', nested: 'none' } : { kind: 'none' },
        });
      }}
    >
      <Popover.Trigger
        render={
          <Button
            ref={triggerRef}
            size="sm"
            className={styles.selector}
            aria-label={`Workspace Settings: ${workspaceLabel(state)}`}
            aria-disabled={unavailable ? true : undefined}
            title={unavailable}
            onClick={(event) => {
              if (unavailable) event.preventDefault();
            }}
          />
        }
      >
        <Settings2 />
        <span className={styles.selectorText}>{workspaceLabel(state)}</span>
        <ChevronDown />
      </Popover.Trigger>
      {state.kind === 'inspectable' && (
        <Popover.Content align="end" className={styles.workspacePopup}>
          <div className={styles.popupHeader}>
            <Popover.Title>Workspace Settings</Popover.Title>
          </div>
          <div className={styles.workspaceBody}>
            <Tabs.Root
              value={state.selectedPreset}
              orientation="vertical"
              onValueChange={(preset) => {
                if (
                  isWorkspacePreset(preset) &&
                  state.presetAvailability[preset].kind === 'available'
                ) {
                  onIntent({ type: 'workspace.preset-changed', preset });
                }
              }}
            >
              <Tabs.List className={styles.presetRail} aria-label="Workspace presets">
                {WORKSPACE_PRESETS.map((preset) => {
                  const availability = state.presetAvailability[preset.id];
                  const reason = availabilityReason(availability);
                  return (
                    <Tabs.Tab
                      key={preset.id}
                      value={preset.id}
                      className={styles.preset}
                      aria-disabled={reason ? true : undefined}
                      title={reason}
                    >
                      <span className={styles.presetLabel}>{preset.label}</span>
                    </Tabs.Tab>
                  );
                })}
              </Tabs.List>
            </Tabs.Root>
            <div className={styles.detail} role="tabpanel">
              <WorkspaceSettingsDetail workspace={state} nested={nested} onIntent={onIntent} />
            </div>
          </div>
          <div className={styles.destination}>
            {state.destination.kind === 'resolving' && <span>Resolving destination…</span>}
            {state.destination.kind === 'ready' && (
              <span>
                {state.destination.path}
                {state.destination.description ? ` · ${state.destination.description}` : ''}
              </span>
            )}
            {state.destination.kind === 'fallback' && (
              <span>
                {state.destination.path} · {state.destination.warning}
              </span>
            )}
            {state.destination.kind === 'unavailable' && (
              <>
                <span>{state.destination.reason}</span>
                <Button
                  size="xs"
                  onClick={() =>
                    onIntent({ type: 'workspace.retry-requested', target: 'destination' })
                  }
                >
                  Retry
                </Button>
              </>
            )}
            {(state.resolution.kind === 'ready-warning' || state.resolution.kind === 'invalid') && (
              <span className={styles.destinationStatus}>{state.resolution.message}</span>
            )}
            {state.resolution.kind === 'recoverably-unavailable' && (
              <span className={styles.destinationStatus}>{state.resolution.reason}</span>
            )}
          </div>
        </Popover.Content>
      )}
    </Popover.Root>
  );
}
