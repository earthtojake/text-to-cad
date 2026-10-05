import { Download } from "lucide-react";
import { useId, useState, type ComponentProps, type ComponentType } from "react";
import type { Popover as PopoverPrimitive } from "radix-ui";
import { Button } from "../primitives/button.jsx";
import { Popover, PopoverContent as PopoverContentPrimitive, PopoverTrigger as PopoverTriggerPrimitive } from "../primitives/popover.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { UpdateCard } from "./UpdateCard.js";
import type { UpdateNotice } from "./useUpdateNotice.js";

// The popover primitives are JavaScript, and forwardRef leaves them no props a type can see: theirs are Radix's.
const PopoverTrigger = PopoverTriggerPrimitive as unknown as ComponentType<ComponentProps<typeof PopoverPrimitive.Trigger>>;
const PopoverContent = PopoverContentPrimitive as unknown as ComponentType<ComponentProps<typeof PopoverPrimitive.Content>>;

/**
 * A newer text-to-cad, as the blue update button: a host hands it to the viewer (`update`), which
 * draws it first among the navbar's controls, an icon, and on the home as a row of its own, labeled
 * Update (`labeled`), while this install is behind (`cadgen/updates.py`, which tells only a copy
 * installed by hand). It opens the update card
 * (`UpdateCard`) in a popover, until the person closes it, sends the prompt or clicks away; nothing
 * there is an answer the server keeps, so the button stays until the update lands.
 */
export function UpdateButton({ notice, send, copy, onLink, align = "end", labeled = false }: {
  notice: UpdateNotice;
  /** Posts the prompt to the chat, where the host can. */
  send?: (prompt: string) => Promise<void>;
  copy(prompt: string): Promise<void>;
  onLink(url: string): void;
  /** Where the card opens against the button: under the navbar's right end, or centred on the home. */
  align?: "start" | "center" | "end";
  /** The word Update beside the icon: the home's call to action. */
  labeled?: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const blue = "bg-blue-500 text-white hover:bg-blue-600 dark:bg-blue-500 dark:hover:bg-blue-400";
  const trigger = labeled
    ? <PopoverTrigger asChild>
      <Button variant="default" size="sm" aria-label={`Update to ${notice.latest}`} data-update=""
        className={`h-7 cursor-pointer gap-1.5 px-2.5 text-xs font-medium ${blue}`}>
        <Download className="size-3.5" aria-hidden="true" />Update
      </Button>
    </PopoverTrigger>
    : <TooltipHint content="Update">
      <PopoverTrigger asChild>
        <Button variant="default" size="icon-xs" aria-label={`Update to ${notice.latest}`} data-update="" className={`size-6 ${blue}`}>
          <Download className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>;
  return <Popover open={open} onOpenChange={setOpen}>
    {trigger}
    {/* The card brings its own surface: the popover is only where it opens. */}
    <PopoverContent align={align} sideOffset={6} aria-labelledby={`${id}-title`} aria-describedby={`${id}-text`}
      className="w-80 max-w-[calc(100vw-1rem)] border-0 bg-transparent p-0 shadow-none">
      <UpdateCard id={id} notice={notice} send={send} copy={copy} onLink={onLink} onClose={() => setOpen(false)} />
    </PopoverContent>
  </Popover>;
}
