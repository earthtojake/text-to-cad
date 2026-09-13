import { MENTION_ICON_PROPS } from './shared';

/** Custom/at mention icon (@). */
export function MentionAtIcon() {
  return (
    <svg {...MENTION_ICON_PROPS}>
      <circle cx="8" cy="8" r="3" />
      <path d="M11 8c0 2.8 2 4 4 3V7A7 7 0 1 0 8 15" />
    </svg>
  );
}
