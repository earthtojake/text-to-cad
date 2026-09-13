import { ROW_H } from '@components/engine/row-metrics';
import { defineUnit } from '@core/units';
import type { TurnOutcomeItem } from '@/model';
import { vars } from '@styles/theme.css';

function outcomeLabel(item: TurnOutcomeItem): string {
  const reason = item.outcome.reason ? ` (${item.outcome.reason})` : '';
  switch (item.outcome.kind) {
    case 'cancelled':
      return `Turn cancelled${reason}`;
    case 'error':
      return `Turn failed${reason}`;
    case 'interrupted':
      return `Turn interrupted${reason}`;
    case 'done':
      return `Turn completed${reason}`;
    default:
      return `Turn finished${reason}`;
  }
}

export const turnOutcomeUnitDef = defineUnit<TurnOutcomeItem, { rowH: number }>({
  kind: 'turn-outcome',
  margin: { top: 4, bottom: 4 },
  vars: { rowH: ROW_H },

  measure(_data, _ctx, vars_) {
    return vars_.rowH;
  },

  Render(props) {
    return (
      <div
        style={{
          height: `${props.vars.rowH}px`,
          display: 'flex',
          'align-items': 'center',
          color: props.data.outcome.kind === 'error' ? vars.fgError : vars.fgMuted,
          'font-size': '13px',
        }}
      >
        {outcomeLabel(props.data)}
      </div>
    );
  },
});
