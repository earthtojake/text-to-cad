import { Check, X } from "lucide-react";

import { Button } from "@renderer/components/ui/button";
import { cn } from "@renderer/lib/utils";
import { useChecklist, useShowChecklist } from "@renderer/state/onboarding";
import { useSettings } from "@renderer/state/settings";

/**
 * The sidebar's Getting started checklist, after the welcome. Each item ticks
 * itself from what the person has done; closing it, or finishing it and
 * pressing Done, hides it for good.
 */
export function GettingStarted() {
  const show = useShowChecklist();
  const items = useChecklist();
  const patch = useSettings((state) => state.patch);

  if (!show) {
    return null;
  }

  const dismiss = () => void patch({ onboardingChecklistDismissed: true });
  const done = items.filter((item) => item.done).length;
  const complete = done === items.length;

  return (
    <section
      aria-label="Getting started"
      className="mx-2 mb-2 shrink-0 rounded-lg border border-sidebar-border bg-sidebar-accent/40 px-3 py-2.5"
      data-onboarding-checklist
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium">
          {complete ? "You're all set" : "Getting started"}
          <span className="ml-1.5 font-normal text-muted-foreground">
            {done}/{items.length}
          </span>
        </p>
        <Button
          aria-label="Close Getting started"
          className="size-5 text-muted-foreground"
          onClick={dismiss}
          size="icon-sm"
          variant="ghost"
        >
          <X className="size-3" />
        </Button>
      </div>
      <ul className="mt-2 space-y-1.5">
        {items.map((item) => (
          <li className="flex items-center gap-2 text-xs" data-done={item.done} key={item.id}>
            <span
              className={cn(
                "flex size-3.5 shrink-0 items-center justify-center rounded-full border",
                item.done ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40",
              )}
            >
              {item.done ? <Check className="size-2.5" strokeWidth={3} /> : null}
            </span>
            <span className={cn(item.done && "text-muted-foreground line-through")}>{item.label}</span>
          </li>
        ))}
      </ul>
      {complete ? (
        <Button className="mt-2.5 h-7 w-full text-xs" onClick={dismiss} size="sm" variant="secondary">
          Done
        </Button>
      ) : null}
    </section>
  );
}
