import { AgentStatus, BrailleSpinner } from '@emdash/ui/react/components';
import { RelativeTime, Tooltip } from '@emdash/ui/react/primitives';
import { Check, CircleAlert, CircleX } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { taskAgentStatus } from '@core/features/conversations/api/browser/conversation-selectors';
import { type TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { getSidebarStore } from '@core/features/workbench/contributions/browser/app-stores';
import type { AgentStatus as AgentStatusKind } from '@core/primitives/agents/api';
import { useDelayedBoolean } from '@core/primitives/react-hooks/browser/use-delay-boolean';
import { getSortInstant, sortKindFor } from './sidebar-store';

/**
 * Sidebar trailing slot: spinner while bootstrapping, the live agent status
 * indicator while an agent is active (non-idle), otherwise the relative
 * timestamp. The whole metadata cluster is right-aligned by the parent, so
 * the slot just hugs its content — no fixed width to avoid an empty gap
 * between the timestamp and the line-changes / PR icon to its left.
 */
function Slot({ children }: { children: React.ReactNode }) {
  return <span className="flex w-[3ch] shrink-0 items-center justify-end">{children}</span>;
}

const STATUS_LABELS = {
  working: 'Working',
  'awaiting-input': 'Needs input',
  error: 'Failed',
  completed: 'Done',
  idle: '',
} as const;

export function SidebarAgentStatusLabel({ status }: { status: AgentStatusKind }) {
  if (status === 'idle') return null;
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 text-micro font-medium ${
        status === 'awaiting-input'
          ? 'text-foreground-warning'
          : status === 'error'
            ? 'text-foreground-destructive'
            : 'text-foreground-muted'
      }`}
      role="status"
      aria-label={STATUS_LABELS[status]}
      title={STATUS_LABELS[status]}
    >
      {status === 'working' ? <AgentStatus status="working" size="0.875rem" /> : null}
      {status === 'awaiting-input' ? <CircleAlert className="size-3" /> : null}
      {status === 'error' ? <CircleX className="size-3" /> : null}
      {status === 'completed' ? <Check className="size-3" /> : null}
      <span>{STATUS_LABELS[status]}</span>
    </span>
  );
}

export const TaskSidebarTrailingSlot = observer(function TaskSidebarTrailingSlot({
  task,
  showTimestamp,
}: {
  task: TaskStore;
  showTimestamp: boolean;
}) {
  const delayedIsBootstrapping = useDelayedBoolean(task.isBootstrapping, 500);

  if (delayedIsBootstrapping) {
    return (
      <Slot>
        <Tooltip.Root>
          <Tooltip.Trigger>
            <span className="flex size-6 items-center justify-center">
              <BrailleSpinner variant="wave" />
            </span>
          </Tooltip.Trigger>
          <Tooltip.Content>Preparing chat workspace…</Tooltip.Content>
        </Tooltip.Root>
      </Slot>
    );
  }

  // Show the agent status indicator for any active/unseen state; fall back to timestamp for null (idle).
  const status = taskAgentStatus(task);
  if (status !== null) {
    return <SidebarAgentStatusLabel status={status} />;
  }

  if (!showTimestamp) return null;

  const instant = getSortInstant(task, sortKindFor(getSidebarStore().taskSortBy));
  if (!instant) return null;

  return (
    <Slot>
      <RelativeTime
        value={instant}
        className="font-sans text-xs text-foreground-passive tabular-nums"
        compact
      />
    </Slot>
  );
});
