import type { JSX } from 'solid-js';
import { Show } from 'solid-js';
import { IconError, IconShieldAlert } from './icons';
import {
  cardChevronExpanded,
  cardErrorIcon,
  cardHeader,
  cardHeaderLeft,
  cardHeaderRight,
  cardHeaderTitle,
  cardHoverChevron,
  cardLeadingIcon,
  cardLeadingSlot,
  cardPermissionIcon,
} from './card-header.css';
import { textShimmer } from '@styles/effects.css';

export type CardHeaderProps = {
  /** Item id wired to data-collapse-id for ChatRoot click delegation. */
  id: string;
  /** Explicit pixel height for the header row. */
  height: number;
  /** Whether the section is currently expanded. */
  expanded: boolean;
  /** Leading icon shown until the header row is hovered. */
  icon: JSX.Element;
  /** Header label content. */
  title: JSX.Element;
  /**
   * When true, applies the text-shimmer animation to the title
   * (use while the item is running / streaming).
   */
  active?: boolean;
  /** When true, renders the error icon on the far right of the header. */
  error?: boolean;
  /** Native tooltip shown when hovering the error icon. */
  errorTitle?: string;
  /** When true, renders the awaiting-permission icon in the right-side status slot. */
  awaitingPermission?: boolean;
  /** Optional right-aligned content beside the status icon. */
  right?: JSX.Element;
};

export function CardHeader(props: CardHeaderProps) {
  return (
    <div
      class={cardHeader}
      style={{ height: `${props.height}px` }}
      role="button"
      aria-expanded={props.expanded ? 'true' : 'false'}
      data-collapse-id={props.id}
    >
      <span class={cardHeaderLeft}>
        <span class={cardLeadingSlot} aria-hidden="true">
          <span class={cardLeadingIcon}>{props.icon}</span>
          <span
            class={cardHoverChevron}
            classList={{ [cardChevronExpanded]: props.expanded }}
            aria-hidden="true"
          >
            ›
          </span>
        </span>
        <span class={cardHeaderTitle} classList={{ [textShimmer]: !!props.active }}>
          {props.title}
        </span>
      </span>
      <span class={cardHeaderRight}>
        {props.right}
        <Show
          when={props.awaitingPermission}
          fallback={
            <Show when={props.error}>
              <span class={cardErrorIcon} title={props.errorTitle ?? 'Failed'} aria-label="error">
                <IconError />
              </span>
            </Show>
          }
        >
          <span
            class={cardPermissionIcon}
            title="Awaiting permission"
            aria-label="awaiting permission"
          >
            <IconShieldAlert />
          </span>
        </Show>
      </span>
    </div>
  );
}
