/**
 * CopyButton — shared copy-to-clipboard button.
 *
 * Two variants:
 *   'inline'  — used in the message footer: text label + icon, appears on group-hover.
 *   'overlay' — used in code blocks: icon-only, absolute positioned top-right.
 *
 * State is managed by createClipboard (Lane B — never touches measure).
 */

import { Show } from 'solid-js';
import { IconCheck, IconCopy } from './icons';
import { createClipboard } from './use-clipboard';
import { copyButtonInline, copyButtonOverlay } from './copy-button.css';

export type CopyButtonProps = {
  text: string;
  variant: 'inline' | 'overlay';
  /** aria-label prefix shown before 'Copy' / 'Copied'. Defaults to 'Copy'. */
  label?: string;
};

export function CopyButton(props: CopyButtonProps) {
  const { copied, copy } = createClipboard();
  const label = () => props.label ?? 'Copy';
  const ariaLabel = () => (copied() ? `${label()} — copied` : label());

  if (props.variant === 'overlay') {
    return (
      <button
        type="button"
        class={copyButtonOverlay}
        aria-label={ariaLabel()}
        onClick={() => copy(props.text)}
      >
        <Show when={copied()} fallback={<IconCopy />}>
          <IconCheck />
        </Show>
      </button>
    );
  }

  return (
    <button
      type="button"
      class={copyButtonInline}
      aria-label={ariaLabel()}
      onClick={() => copy(props.text)}
    >
      <Show when={copied()} fallback={<IconCopy />}>
        <IconCheck />
      </Show>
      <span>{copied() ? 'Copied' : 'Copy'}</span>
    </button>
  );
}
