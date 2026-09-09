import { MENTION_ICON_PROPS } from './shared';

/** Symbol mention icon (curly braces). */
export function MentionSymbolIcon() {
  return (
    <svg {...MENTION_ICON_PROPS}>
      <path d="M5 2C3.9 2 3 2.9 3 4v2c0 1.1-.9 2-2 2 1.1 0 2 .9 2 2v2c0 1.1.9 2 2 2" />
      <path d="M11 2c1.1 0 2 .9 2 2v2c0 1.1.9 2 2 2-1.1 0-2 .9-2 2v2c0 1.1-.9 2-2 2" />
    </svg>
  );
}
