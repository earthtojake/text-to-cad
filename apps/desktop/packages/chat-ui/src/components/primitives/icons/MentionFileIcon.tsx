import { MENTION_ICON_PROPS } from './shared';

/** File mention icon (document with folded corner). */
export function MentionFileIcon() {
  return (
    <svg {...MENTION_ICON_PROPS}>
      <path d="M9 2H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6L9 2z" />
      <polyline points="9 2 9 6 13 6" />
    </svg>
  );
}
