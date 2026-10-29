import { Download } from "lucide-react";
import { useId, useState, type ComponentProps, type ComponentType } from "react";
import type { Popover as PopoverPrimitive } from "radix-ui";
import { Button } from "../primitives/button.jsx";
import { Popover, PopoverContent as PopoverContentPrimitive, PopoverTrigger as PopoverTriggerPrimitive } from "../primitives/popover.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useI18n } from "../i18n/index.js";
import { UpdateCard } from "./UpdateCard.js";
import { readUpdateNotice, updateShows, type UpdateNotice, type UpdateStart } from "./useUpdateNotice.js";

// The popover primitives are JavaScript, and forwardRef leaves them no props a type can see: theirs are Radix's.
const PopoverTrigger = PopoverTriggerPrimitive as unknown as ComponentType<ComponentProps<typeof PopoverPrimitive.Trigger>>;
const PopoverContent = PopoverContentPrimitive as unknown as ComponentType<ComponentProps<typeof PopoverPrimitive.Content>>;

/**
 * A newer text-to-cad, as the blue update button: a host hands it to the viewer (`update`), which
 * draws it first among the navbar's controls, an icon, over every file and over the home, while
 * the notice leaves the person something to do (`updateShows`: the command for a copy the engine
 * does not update, Try again once the engine's update failed); an update pending or under way is the
 * engine's, and draws nothing, as one installed does: the next thread, session or page runs it. It opens the update card
 * (`UpdateCard`) in a popover, reading the server's notice again as it opens, until the person closes
 * it, sends the prompt or clicks away. An open card stays while what it shows moves on: a run it
 * started shows its progress there, whatever the button would do meanwhile.
 */
export function UpdateButton({ notice, send, copy, onLink, update }: {
  notice: UpdateNotice;
  /** Posts the prompt to the chat, where the host can. */
  send?: (prompt: string) => Promise<void>;
  /** Copies the command. */
  copy(text: string): Promise<void>;
  onLink(url: string): void;
  /** Starts the engine's update again (the failed card's Try again). */
  update?: UpdateStart;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  if (!open && !updateShows(notice)) return null;
  const blue = "bg-blue-500 text-white hover:bg-blue-600 dark:bg-blue-500 dark:hover:bg-blue-400";
  return <Popover open={open} onOpenChange={(next: boolean) => { setOpen(next); if (next) readUpdateNotice(); }}>
    <TooltipHint content={t("update.label")}>
      <PopoverTrigger asChild>
        <Button variant="default" size="icon-xs" aria-label={t("update.toAria", { version: notice.latest })} data-update="" className={`size-6 ${blue}`}>
          <Download className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    {/* The card brings its own surface: the popover is only where it opens. */}
    <PopoverContent align="end" sideOffset={6} aria-labelledby={`${id}-title`} aria-describedby={`${id}-text`}
      className="w-80 max-w-[calc(100vw-1rem)] border-0 bg-transparent p-0 shadow-none">
      <UpdateCard id={id} notice={notice} send={send} copy={copy} onLink={onLink} update={update} onClose={() => setOpen(false)} />
    </PopoverContent>
  </Popover>;
}
