import type { PopoverRootChangeEventDetails } from '@base-ui/react/popover';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { Popover } from '@emdash/ui/react/primitives';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AgentInfoCard } from '@core/features/agents/browser/components/agent-selector/agent-info-card';

const OPEN_DELAY_MS = 500;
const CLOSE_DELAY_MS = 200;

const HOVER_CARD_ATTR = 'data-agent-hover-card';

/**
 * True when a dismissal event originated inside the agent hover card or inside a popup
 * spawned from it (e.g. the install-method select, which portals to document.body and
 * therefore fails plain DOM containment checks against the card).
 *
 * `ownPopup` is the popup element of the surrounding agent list itself; clicks inside it
 * are never attributed to the hover card.
 */
export function isEventInsideAgentHoverCard(
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
      '[data-slot="popover-content"], [data-slot="combobox-content"], [data-slot="dropdown-menu-content"]'
    );
    return popup !== null && popup !== ownPopup;
  });
}

/**
 * True while the user is actively engaged with the hover card: typing in one of its
 * inputs, or a nested popup (install-method select) opened from it is expanded.
 * Used to suppress the hover-out close timer mid-interaction.
 */
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

interface RowHoverProps {
  onMouseEnter: (event: React.MouseEvent<HTMLElement>) => void;
  onMouseLeave: () => void;
}

export interface AgentHoverCardController {
  open: boolean;
  activeId: AgentProviderId | null;
  getRowHoverProps: (id: AgentProviderId) => RowHoverProps;
  popupHoverProps: RowHoverProps;
  handleOpenChange: (open: boolean) => void;
  close: () => void;
}

/**
 * Shared hover-card timing for the agent list. A single card is shown after a
 * one-second delay on first hover; while it is open, hovering other rows swaps
 * the content instantly instead of reopening. Moving onto the card keeps it open
 * so its links/copy button stay interactive.
 */
export function useAgentHoverCard(): AgentHoverCardController {
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<AgentProviderId | null>(null);
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
      // Keep the card open while the user is typing in it or has a nested popup open.
      if (isHoverCardEngaged()) return;
      setOpenState(false);
    }, CLOSE_DELAY_MS);
  }, [clearCloseTimer, setOpenState]);

  const handleRowEnter = useCallback(
    (id: AgentProviderId) => {
      clearCloseTimer();
      setActiveId(id);
      // Already warm → just switched content, no reopen and no delay.
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
    (id: AgentProviderId): RowHoverProps => ({
      onMouseEnter: () => handleRowEnter(id),
      onMouseLeave: handleRowLeave,
    }),
    [handleRowEnter, handleRowLeave]
  );

  const popupHoverProps: RowHoverProps = {
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

  return {
    open,
    activeId,
    getRowHoverProps,
    popupHoverProps,
    handleOpenChange,
    close,
  };
}

interface AgentHoverCardProps {
  anchor: HTMLElement | null;
  controller: AgentHoverCardController;
  connectionId?: string;
  side?: 'top' | 'bottom' | 'left' | 'right';
  align?: 'start' | 'center' | 'end';
}

/** Single shared hover card anchored beside the combobox panel. */
export const AgentHoverCard: React.FC<AgentHoverCardProps> = ({
  anchor,
  controller,
  connectionId,
  side = 'right',
  align = 'start',
}) => {
  const { open, activeId, popupHoverProps, handleOpenChange } = controller;

  const onOpenChange = useCallback(
    (next: boolean, eventDetails: PopoverRootChangeEventDetails) => {
      // Interactions with popups spawned from the card (install-method select) register
      // as outside presses on this popover; keep the card open for them.
      if (!next && isEventInsideAgentHoverCard(eventDetails.event, anchor)) {
        eventDetails.cancel();
        return;
      }
      handleOpenChange(next);
    },
    [anchor, handleOpenChange]
  );

  if (!anchor || !activeId) return null;

  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Content
        {...{ [HOVER_CARD_ATTR]: '' }}
        anchor={anchor}
        side={side}
        align={align}
        sideOffset={8}
        initialFocus={false}
        finalFocus={false}
        className="w-auto p-0 text-foreground"
        onMouseEnter={popupHoverProps.onMouseEnter}
        onMouseLeave={popupHoverProps.onMouseLeave}
      >
        <AgentInfoCard id={activeId} connectionId={connectionId} />
      </Popover.Content>
    </Popover.Root>
  );
};
