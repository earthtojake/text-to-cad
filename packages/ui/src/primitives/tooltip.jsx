"use client"

import * as React from "react"
import { Tooltip as TooltipPrimitive, Slot } from "radix-ui"

import { cn } from "@hardcore/ui/utils"

function TooltipProvider({
  delayDuration = 400,
  ...props
}) {
  return (<TooltipPrimitive.Provider data-slot="tooltip-provider" delayDuration={delayDuration} {...props} />);
}

function Tooltip({
  ...props
}) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

const TooltipTrigger = React.forwardRef(function TooltipTrigger({
  ...props
}, ref) {
  return <TooltipPrimitive.Trigger ref={ref} data-slot="tooltip-trigger" {...props} />;
});

const TooltipContent = React.forwardRef(function TooltipContent({
  className,
  arrowClassName,
  sideOffset = 0,
  children,
  ...props
}, ref) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        ref={ref}
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "pointer-events-none z-50 w-fit max-w-64 origin-(--radix-tooltip-content-transform-origin) animate-in rounded-md border border-border bg-popover px-3 py-1.5 text-tiny leading-4 text-balance text-popover-foreground shadow-lg shadow-black/10 fade-in-0 zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
          className
        )}
        {...props}>
        {children}
        <TooltipPrimitive.Arrow
          className={cn(
            "z-50 size-2.5 translate-y-[calc(-50%_-_2px)] rotate-45 rounded-[2px] bg-popover fill-popover",
            arrowClassName
          )} />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
});

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }

// A hint on focus answers keyboard NAVIGATION: a Tab onto the control. Focus that a closing
// menu or popover hands back to its trigger (after Escape, or a choice) is restoration, and
// reopening the trigger's hint then reads as a hint that "sticks". So whether the last key
// was Tab is tracked, in every document a hint is mounted in, and a pointer press clears it.
let focusArrivedByTab = false;
const navigationDocuments = new WeakSet();
function trackFocusNavigation(document) {
  if (!document || navigationDocuments.has(document)) return;
  navigationDocuments.add(document);
  document.addEventListener("keydown", event => { focusArrivedByTab = event.key === "Tab"; }, true);
  document.addEventListener("pointerdown", () => { focusArrivedByTab = false; }, true);
}

/** Short, noninteractive hints. Never use a native title alongside this component. */
/** @typedef {Omit<React.HTMLAttributes<HTMLElement>, "content" | "children"> & { content?: React.ReactNode, children: React.ReactElement, disabled?: boolean, side?: "top" | "right" | "bottom" | "left", overflowOnly?: boolean }} TooltipHintProps */
const TooltipHint = React.forwardRef(/**
 * @param {TooltipHintProps} props
 * @param {React.ForwardedRef<HTMLElement>} forwardedRef
 */ function TooltipHint({ content, children, disabled = false, side = "bottom", overflowOnly = false, ...props }, forwardedRef) {
  const [open, setOpen] = React.useState(false);
  const blocked = disabled || !content || children.props.disabled || children.props["aria-expanded"] === true || props["aria-expanded"] === true;
  React.useEffect(() => { if (blocked) setOpen(false); }, [blocked]);
  const target = React.useRef(null);
  React.useEffect(() => { trackFocusNavigation(target.current?.ownerDocument); }, []);
  const bindTarget = React.useCallback(node => {
    target.current = node;
    if (typeof forwardedRef === "function") forwardedRef(node);
    else if (forwardedRef) forwardedRef.current = node;
  }, [forwardedRef]);
  const isClipped = () => {
    const node = target.current;
    return node && [node, ...node.querySelectorAll('.truncate')].some(element => element.scrollWidth > element.clientWidth + 1);
  };
  if (!content) return <Slot.Root {...props} ref={forwardedRef}>{children}</Slot.Root>;
  const unavailable = () => target.current?.matches(':disabled, [aria-disabled="true"], [aria-expanded="true"]')
    || target.current?.closest('[inert]') || target.current?.querySelector('[aria-expanded="true"], :disabled');
  return <TooltipProvider delayDuration={400} skipDelayDuration={0}>
    <Tooltip open={!blocked && open} onOpenChange={next => setOpen(!blocked && next && !unavailable() && (!overflowOnly || isClipped()))} disableHoverableContent>
      <TooltipTrigger asChild {...props} ref={bindTarget}
        onPointerDown={event => { setOpen(false); props.onPointerDown?.(event); }}
        onClick={event => { setOpen(false); props.onClick?.(event); }}
        onFocus={event => { props.onFocus?.(event); if (!focusArrivedByTab || !event.currentTarget.matches(':focus-visible')) event.preventDefault(); }}>
        {children}
      </TooltipTrigger>
      {!blocked && open ? <TooltipContent side={side} sideOffset={6} className="pointer-events-none">{content}</TooltipContent> : null}
    </Tooltip>
  </TooltipProvider>;
});

export { TooltipHint };
