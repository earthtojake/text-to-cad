import { BlockStackView } from '@components/primitives/BlockStackView';
import {
  PlanCompletedIcon,
  PlanInProgressIcon,
  PlanPendingIcon,
} from '@components/primitives/icons';
import { Match, Switch, For } from 'solid-js';
import type { PlanEntryPriority, PlanEntryStatus } from '@/model';
import type { PlanEntryLaid } from './plan.def';
import { planVars } from './plan.css';

// ── Status glyph helpers ──────────────────────────────────────────────────────

function statusColor(status: PlanEntryStatus): string {
  if (status === 'completed') return 'var(--chat-plan-done, #22c55e)';
  if (status === 'in_progress') return 'var(--chat-plan-active, #f59e0b)';
  return 'var(--chat-fg-passive, currentColor)';
}

function priorityOpacity(priority: PlanEntryPriority): string {
  if (priority === 'low') return '0.55';
  return '1';
}

// ── PlanList ──────────────────────────────────────────────────────────────────

export type PlanListProps = {
  entries: PlanEntryLaid[];
};

export function PlanList(props: PlanListProps) {
  return (
    <div
      style={{
        'padding-top': planVars.padY,
        'padding-bottom': planVars.padY,
      }}
    >
      <For each={props.entries}>
        {(entry, i) => (
          <div
            style={{
              display: 'flex',
              'align-items': 'flex-start',
              'column-gap': planVars.iconGap,
              'margin-top': i() > 0 ? planVars.entryGap : '0',
              opacity: priorityOpacity(entry.priority),
            }}
          >
            <div
              style={{
                width: planVars.iconBox,
                height: '20px',
                'flex-shrink': '0',
                display: 'flex',
                'align-items': 'center',
                'justify-content': 'center',
                color: statusColor(entry.status),
                'user-select': 'none',
              }}
              aria-label={entry.status.replace('_', ' ')}
            >
              <Switch>
                <Match when={entry.status === 'completed'}>
                  <PlanCompletedIcon />
                </Match>
                <Match when={entry.status === 'in_progress'}>
                  <PlanInProgressIcon />
                </Match>
                <Match when={entry.status === 'pending'}>
                  <PlanPendingIcon />
                </Match>
              </Switch>
            </div>
            <div style={{ flex: '1' }}>
              <BlockStackView node={entry.measured} />
            </div>
          </div>
        )}
      </For>
    </div>
  );
}
