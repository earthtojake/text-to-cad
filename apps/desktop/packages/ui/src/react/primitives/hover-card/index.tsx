/**
 * Hover-card primitives for row-level detail panels.
 *
 * Provides a delay-based open/close controller (`useHoverCard`) and a
 * `HoverCard` component that renders a Popover-anchored detail panel beside a
 * list. Designed to compose with `ComboboxPopover` (or any list-based UI) so
 * that hovering a row shows a detail card while keeping the parent popup open.
 *
 * Key behaviors:
 *  - Open after OPEN_DELAY_MS on first hover; while warm, hovering another row
 *    swaps content instantly with no re-open delay.
 *  - Moving the pointer onto the card itself cancels the close timer so links
 *    and interactive controls inside the card stay reachable.
 *  - Interactions with nested portals spawned by the card (e.g. inner selects)
 *    do not dismiss the card or the parent popup.
 */

import type { PopoverRootChangeEventDetails } from '@base-ui/react/popover';
import { Popover } from '@react/primitives/popover';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { hoverCardDefault } from './hover-card.css';

// ── Constants ─────────────────────────────────────────────────────────────────

const OPEN_DELAY_MS = 500;
const CLOSE_DELAY_MS = 200;
const HOVER_CARD_ATTR = 'data-hover-card';

// ── Helper ────────────────────────────────────────────────────────────────────

/**
 * Returns true when `event` originates inside a `[data-hover-card]` element or
 * inside a portaled popup spawned from one (e.g. an inner Select that renders
 * to document.body), but NOT inside `ownPopup` — that is the parent list's own
 * popup element, which should never be attributed to the hover card.
 */
export function isEventInsideInteractiveLayer(
  event: Event | null | undefined,
  ownPopup: HTMLElement | null
): boolean {
  if (!event) return false;
  const targets: Element[] = [];
  if (event.target instanceof Element) targets.push(event.target);
  const related = (event as FocusEvent).relatedTarget;
  if (related instanceof Element) targets.push(related);
  return targets.some((el) => {
    if (el.closest(`[${HOVER_CARD_ATTR}]`)) return true;
    const popup = el.closest(
      '[data-slot="popover-content"],[data-slot="combobox-content"],[data-slot="dropdown-menu-content"]'
    );
    return popup !== null && popup !== ownPopup;
  });
}

// ── Controller ────────────────────────────────────────────────────────────────

export interface HoverCardRowProps {
  onMouseEnter: (event: React.MouseEvent<HTMLElement>) => void;
  onMouseLeave: () => void;
}

export interface HoverCardController {
  open: boolean;
  activeKey: string | null;
  getRowHoverProps: (key: string) => HoverCardRowProps;
  popupHoverProps: HoverCardRowProps;
  handleOpenChange: (open: boolean) => void;
  close: () => void;
}

/** Returns true while the user is actively engaged inside the hover card. */
function isHoverCardEngaged(): boolean {
  const card = document.querySelector(`[${HOVER_CARD_ATTR}]`);
  if (!card) return false;
  if (card.querySelector('[aria-expanded="true"]')) return true;
  const active = document.activeElement;
  return (
    active instanceof HTMLElement &&
    card.contains(active) &&
    (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')
  );
}

/**
 * Hover-card timing controller.
 *
 * Tracks which list row (by `key`) should show a detail card, with debounced
 * open and close delays so the card doesn't flicker on quick mouse moves.
 */
export function useHoverCard(): HoverCardController {
  const [open, setOpen] = useState(false);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const openRef = useRef(false);
  const openTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);

  const setOpenState = useCallback((next: boolean) => {
    openRef.current = next;
    setOpen(next);
  }, []);

  const clearOpenTimer = useCallback(() => {
    if (openTimer.current !== null) {
      window.clearTimeout(openTimer.current);
      openTimer.current = null;
    }
  }, []);

  const clearCloseTimer = useCallback(() => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  useEffect(
    () => () => {
      clearOpenTimer();
      clearCloseTimer();
    },
    [clearOpenTimer, clearCloseTimer]
  );

  const scheduleClose = useCallback(() => {
    clearCloseTimer();
    closeTimer.current = window.setTimeout(() => {
      closeTimer.current = null;
      if (isHoverCardEngaged()) return;
      setOpenState(false);
    }, CLOSE_DELAY_MS);
  }, [clearCloseTimer, setOpenState]);

  const handleRowEnter = useCallback(
    (key: string) => {
      clearCloseTimer();
      setActiveKey(key);
      // While warm: swap content instantly without reopening.
      if (openRef.current) return;
      if (openTimer.current === null) {
        openTimer.current = window.setTimeout(() => {
          openTimer.current = null;
          setOpenState(true);
        }, OPEN_DELAY_MS);
      }
    },
    [clearCloseTimer, setOpenState]
  );

  const handleRowLeave = useCallback(() => {
    clearOpenTimer();
    scheduleClose();
  }, [clearOpenTimer, scheduleClose]);

  const getRowHoverProps = useCallback(
    (key: string): HoverCardRowProps => ({
      onMouseEnter: () => handleRowEnter(key),
      onMouseLeave: handleRowLeave,
    }),
    [handleRowEnter, handleRowLeave]
  );

  const popupHoverProps: HoverCardRowProps = {
    onMouseEnter: clearCloseTimer,
    onMouseLeave: scheduleClose,
  };

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) {
        clearOpenTimer();
        clearCloseTimer();
      }
      setOpenState(next);
    },
    [clearOpenTimer, clearCloseTimer, setOpenState]
  );

  const close = useCallback(() => {
    clearOpenTimer();
    clearCloseTimer();
    setOpenState(false);
  }, [clearOpenTimer, clearCloseTimer, setOpenState]);

  return { open, activeKey, getRowHoverProps, popupHoverProps, handleOpenChange, close };
}

// ── Component ─────────────────────────────────────────────────────────────────

export interface HoverCardProps {
  /** Popover anchor — the element the card is positioned relative to. */
  anchor: HTMLElement | null;
  /** The parent list's own popup element, used to exclude it from
   * `isEventInsideInteractiveLayer` checks so the card doesn't eat the list's
   * own dismissal events. */
  ownPopup?: HTMLElement | null;
  controller: HoverCardController;
  children: React.ReactNode;
  side?: 'top' | 'bottom' | 'left' | 'right';
  align?: 'start' | 'center' | 'end';
  sideOffset?: number;
  className?: string;
}

/**
 * A shared detail card anchored beside a list popup.
 *
 * Wraps `PopoverContent` and applies `data-hover-card` so that
 * `isEventInsideInteractiveLayer` can detect focus/click events inside it.
 * Cancels its own close when interactions occur inside nested portals (e.g.
 * inner selects), and forwards `popupHoverProps` to maintain the keep-open
 * timing while the pointer is on the card.
 */
export function HoverCard({
  anchor,
  ownPopup,
  controller,
  children,
  side = 'right',
  align = 'start',
  sideOffset = 8,
  className,
}: HoverCardProps) {
  const { open, popupHoverProps, handleOpenChange } = controller;

  const onOpenChange = useCallback(
    (next: boolean, eventDetails: PopoverRootChangeEventDetails) => {
      if (!next && isEventInsideInteractiveLayer(eventDetails.event, ownPopup ?? null)) {
        eventDetails.cancel();
        return;
      }
      handleOpenChange(next);
    },
    [ownPopup, handleOpenChange]
  );

  if (!anchor) return null;

  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Content
        {...{ [HOVER_CARD_ATTR]: '' }}
        anchor={anchor}
        side={side}
        align={align}
        sideOffset={sideOffset}
        className={className ?? hoverCardDefault}
        onMouseEnter={popupHoverProps.onMouseEnter}
        onMouseLeave={popupHoverProps.onMouseLeave}
      >
        {children}
      </Popover.Content>
    </Popover.Root>
  );
}
