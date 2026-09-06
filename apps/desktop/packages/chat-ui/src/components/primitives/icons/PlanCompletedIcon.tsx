import { PLAN_ICON_PROPS } from './shared';

/** Completed: stroke circle with a check mark in the middle. */
export function PlanCompletedIcon() {
  return (
    <svg {...PLAN_ICON_PROPS}>
      <circle cx="7" cy="7" r="6" />
      <path d="M4.5 7.2 6.2 9 9.6 5" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  );
}
