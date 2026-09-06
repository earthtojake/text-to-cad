import { PLAN_ICON_PROPS } from './shared';

/** Error: stroke circle with an X, used on tool-call rows with status === 'error'. */
export function IconError() {
  return (
    <svg {...PLAN_ICON_PROPS} stroke-width="1.5">
      <circle cx="7" cy="7" r="6" />
      <path d="M5 5l4 4M9 5l-4 4" stroke-linecap="round" />
    </svg>
  );
}
