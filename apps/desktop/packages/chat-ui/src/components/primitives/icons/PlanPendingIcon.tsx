import { PLAN_ICON_PROPS } from './shared';

/** Pending: dotted stroke circle. */
export function PlanPendingIcon() {
  return (
    <svg {...PLAN_ICON_PROPS}>
      <circle cx="7" cy="7" r="6" stroke-linecap="round" stroke-dasharray="1 3" />
    </svg>
  );
}
