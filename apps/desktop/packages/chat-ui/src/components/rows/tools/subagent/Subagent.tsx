import { clsx } from 'clsx';
import { createSignal, onCleanup, onMount, Show } from 'solid-js';
import type { ChatSubagentToolCall, SubagentPhase } from '@/model';
import {
  subagentChevron,
  subagentChevronExpanded,
  subagentDotCompleted,
  subagentDotFailed,
  subagentHeader,
  subagentIndicator,
  subagentName,
  subagentNameRow,
  subagentStatusDetail,
  subagentStatusRow,
  subagentStatusRowCollapsible,
} from './subagent.css';
import { textShimmer } from '@styles/effects.css';

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const SPINNER_INTERVAL_MS = 80;

const PHASE_LABELS: Record<SubagentPhase, string> = {
  spawning: 'Spawning',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
};

function SubagentProgressIndicator(props: { phase: SubagentPhase }) {
  const [frame, setFrame] = createSignal(0);

  onMount(() => {
    if (props.phase !== 'spawning' && props.phase !== 'running') return;
    const interval = window.setInterval(() => {
      setFrame((value) => (value + 1) % SPINNER_FRAMES.length);
    }, SPINNER_INTERVAL_MS);
    onCleanup(() => window.clearInterval(interval));
  });

  return (
    <span class={subagentIndicator} aria-label={PHASE_LABELS[props.phase]}>
      <Show
        when={props.phase === 'completed' || props.phase === 'failed'}
        fallback={SPINNER_FRAMES[frame()]}
      >
        <span
          class={props.phase === 'completed' ? subagentDotCompleted : subagentDotFailed}
          title={PHASE_LABELS[props.phase]}
        />
      </Show>
    </span>
  );
}

export function SubagentHeader(props: {
  item: ChatSubagentToolCall;
  height: number;
  expanded?: boolean;
  collapsible?: boolean;
}) {
  const label = () => PHASE_LABELS[props.item.phase];
  const name = () => (props.item.background ? `${props.item.name} (background)` : props.item.name);

  return (
    <div class={subagentHeader} style={{ height: `${props.height}px` }}>
      <div class={subagentNameRow}>
        <SubagentProgressIndicator phase={props.item.phase} />
        <span
          class={clsx(subagentName, props.item.status === 'running' && textShimmer)}
          title={name()}
        >
          {name()}
        </span>
      </div>
      <div
        class={clsx(subagentStatusRow, props.collapsible && subagentStatusRowCollapsible)}
        data-collapse-id={props.collapsible ? props.item.id : undefined}
        role={props.collapsible ? 'button' : undefined}
        aria-expanded={props.collapsible ? Boolean(props.expanded) : undefined}
        title={props.item.phase === 'failed' ? (props.item.error ?? 'Failed') : undefined}
      >
        <span>{label()}</span>
        <Show when={props.item.outputPreview}>
          <span class={subagentStatusDetail} title={props.item.outputPreview}>
            · {props.item.outputPreview}
          </span>
        </Show>
        <Show when={props.collapsible}>
          <span class={clsx(subagentChevron, props.expanded && subagentChevronExpanded)}>›</span>
        </Show>
      </div>
    </div>
  );
}
