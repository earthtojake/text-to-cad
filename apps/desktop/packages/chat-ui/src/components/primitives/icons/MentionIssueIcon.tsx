import { MENTION_ICON_PROPS } from './shared';

/** Issue mention icon (circle with dot). */
export function MentionIssueIcon() {
  return (
    <svg {...MENTION_ICON_PROPS}>
      <circle cx="8" cy="8" r="5" />
      <circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  );
}
