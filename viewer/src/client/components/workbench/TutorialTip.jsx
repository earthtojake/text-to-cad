import { useEffect, useRef, useState } from "react";
import { Lightbulb, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { cn } from "@/ui/utils";
import { markTutorialTipSeen, tutorialTipSeen } from "@/workbench/persistence";

// A one-shot coach mark pointing at a control the user has just made relevant.
//
// Only the close button retires it. Clicking away, pressing Escape, or losing
// the selection do not count as "read", so the tip is recorded as seen on
// dismissal and comes back on the next chance until then. The anchored control
// stays fully clickable — this is not a trigger, so copying is one click away.
export default function TutorialTip({
  tipId,
  active = false,
  side = "left",
  align = "center",
  className,
  children
}) {
  const [open, setOpen] = useState(false);
  // Storage is only written on dismiss, so this also guards against reopening
  // within the session between the click and the next render.
  const dismissedRef = useRef(false);

  useEffect(() => {
    if (!tipId || dismissedRef.current) {
      return;
    }
    // Without an anchored control there is nothing to point at.
    if (!active) {
      setOpen(false);
      return;
    }
    if (tutorialTipSeen(tipId)) {
      dismissedRef.current = true;
      return;
    }
    setOpen(true);
  }, [active, tipId]);

  const dismiss = () => {
    dismissedRef.current = true;
    markTutorialTipSeen(tipId);
    setOpen(false);
  };

  return (
    <Popover open={open}>
      <PopoverAnchor asChild>
        {children}
      </PopoverAnchor>
      <PopoverContent
        side={side}
        align={align}
        sideOffset={8}
        collisionPadding={16}
        // Inverted against the scene so a first-run tip reads as an overlay on
        // the app rather than another panel of it. The glass surface is opted
        // out of rather than overridden — it sets its background !important.
        glass={false}
        className={cn(
          "w-[min(44rem,calc(100vw-2rem))] border-transparent bg-foreground px-3 py-2.5 text-background shadow-lg shadow-black/25",
          className
        )}
        // A coach mark must not steal focus from whatever the user is doing, and
        // it should never block a click on the control it is describing.
        onOpenAutoFocus={(event) => event.preventDefault()}
        onCloseAutoFocus={(event) => event.preventDefault()}
        // Only the close button retires the tip. Radix would otherwise dismiss
        // it on the very first click into the scene — which is exactly what the
        // user is being invited to do — so every ambient close is refused.
        // Preventing these blocks the close, not the interaction itself.
        onPointerDownOutside={(event) => event.preventDefault()}
        onInteractOutside={(event) => event.preventDefault()}
        onFocusOutside={(event) => event.preventDefault()}
        onEscapeKeyDown={(event) => event.preventDefault()}
      >
        <div className="flex items-start gap-2">
          <Lightbulb className="mt-px size-4 shrink-0 text-background/70" strokeWidth={2} aria-hidden="true" />
          <p className="min-w-0 flex-1 text-[13px] leading-snug">
            Copy references into prompts to edit specific parts of a STEP file, e.g. &quot;Make the hole{" "}
            <code className="rounded-sm bg-background/20 px-1 py-0.5 font-mono text-[12px]">bracket#o1.1</code>
            {" "}twice as wide&quot;
          </p>
          {/* The only way out — nothing else closes the tip. */}
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="-mr-1 -mt-0.5 size-5 shrink-0 text-background/70 hover:bg-background/15 hover:text-background"
            aria-label="Dismiss tip"
            title="Dismiss"
            onClick={dismiss}
          >
            <X className="size-3.5" strokeWidth={2} aria-hidden="true" />
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
