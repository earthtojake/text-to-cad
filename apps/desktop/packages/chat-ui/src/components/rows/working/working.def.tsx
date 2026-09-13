import { ROW_H } from '@components/engine/row-metrics';
import { defineUnit } from '@core/units';
import type { WorkingItem } from '@/model';
import { vars } from '@styles/theme.css';

export const workingUnitDef = defineUnit<WorkingItem, { rowH: number }>({
  kind: 'working',
  margin: { top: 2, bottom: 2 },
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
          color: vars.fgMuted,
          'font-size': '13px',
        }}
      >
        Working…
      </div>
    );
  },
});
