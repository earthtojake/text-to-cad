import { ArrowUp, Check, Copy, Download, X } from "lucide-react";
import { useId, useState, type ComponentProps, type ComponentType } from "react";
import type { Popover as PopoverPrimitive } from "radix-ui";
import { Button } from "../primitives/button.jsx";
import { Popover, PopoverContent as PopoverContentPrimitive, PopoverTrigger as PopoverTriggerPrimitive } from "../primitives/popover.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useI18n } from "../i18n/index.js";
import { updatePrompt, type UpdateNotice } from "./prompt.js";

// The popover primitives are JavaScript, and forwardRef leaves them no props a type can see: theirs are Radix's.
const PopoverTrigger = PopoverTriggerPrimitive as unknown as ComponentType<ComponentProps<typeof PopoverPrimitive.Trigger>>;
const PopoverContent = PopoverContentPrimitive as unknown as ComponentType<ComponentProps<typeof PopoverPrimitive.Content>>;

/**
 * The update nudge: a newer version is known (the server's `notice`), so the host hands the viewer this
 * blue icon button (`update`), last and outermost among the navbar's controls (the CAD app's file
 * handler, which has no navbar: its corner, under Full size). A press opens a popover that says so and
 * hands the person the prompt for their agent (`updatePrompt`): **Send to agent** where the host can
 * post it to the chat (`send`), else **Copy prompt**; a copy icon on the prompt either way. Nothing here
 * installs, downloads or restarts anything: the agent updates, when the person asks it to. The host
 * draws the button only while a notice is known: nothing at all otherwise.
 */
export function UpdateButton({ notice, send, copy }: {
  notice: UpdateNotice;
  /** Posts the prompt to the chat as the person's message, where the host can. */
  send?: (prompt: string) => Promise<void>;
  /** Puts the prompt on the clipboard. */
  copy(prompt: string): Promise<void>;
}) {
  const id = useId();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const blue = "bg-blue-500 text-white hover:bg-blue-600 dark:bg-blue-500 dark:hover:bg-blue-400";
  return <Popover open={open} onOpenChange={setOpen}>
    <TooltipHint content={t("update.available")}>
      <PopoverTrigger asChild>
        <Button variant="default" size="icon-xs" aria-label={t("update.aria", { version: notice.latest })} data-update="" className={`size-6 ${blue}`}>
          <Download className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    <PopoverContent align="end" sideOffset={6} aria-labelledby={`${id}-title`} aria-describedby={`${id}-text`}
      className="w-80 max-w-[calc(100vw-1rem)] p-3 text-ui">
      {/* Mounted while open alone: each opening starts with nothing copied or refused. */}
      <UpdateCard id={id} notice={notice} send={send} copy={copy} onClose={() => setOpen(false)} />
    </PopoverContent>
  </Popover>;
}

function UpdateCard({ id, notice, send, copy, onClose }: {
  id: string; notice: UpdateNotice; send?: (prompt: string) => Promise<void>; copy(prompt: string): Promise<void>; onClose(): void;
}) {
  const { t } = useI18n();
  const prompt = updatePrompt(notice);
  const [state, setState] = useState<{ busy?: boolean; copied?: boolean; unsent?: boolean; message?: string }>({});
  // Send where the host takes messages and it has not refused one; Copy prompt elsewhere.
  const sends = Boolean(send) && !state.unsent;
  const sendPrompt = async () => {
    setState(previous => ({ ...previous, busy: true }));
    try {
      await send!(prompt);
      onClose();
    } catch {
      setState({ unsent: true, message: t("update.sendFailed") });
    }
  };
  const copyPrompt = async () => {
    setState(previous => ({ ...previous, busy: true }));
    try {
      await copy(prompt);
      setState(previous => ({ unsent: previous.unsent, copied: true, message: t("update.copiedHint") }));
    } catch {
      setState(previous => ({ unsent: previous.unsent, message: t("update.copyFailed") }));
    }
  };
  return <div className="flex flex-col gap-2" data-update-card="">
    <div className="flex items-center justify-between gap-2">
      <h2 id={`${id}-title`} className="font-medium">{t("update.available")}</h2>
      <Button variant="ghost" size="icon-xs" className="-mr-1" aria-label={t("update.close")} onClick={onClose}><X aria-hidden="true" /></Button>
    </div>
    <p id={`${id}-text`} className="text-xs text-muted-foreground">{t("update.description")}</p>
    <div className="relative rounded-sm bg-muted" data-update-prompt="">
      <p className="select-text py-1 pl-2 pr-8 font-mono text-xs text-foreground [overflow-wrap:anywhere]">{prompt}</p>
      <TooltipHint content={state.copied ? t("update.copied") : t("update.copy")} side="bottom">
        <Button variant="ghost" size="icon-xs" className="absolute right-1 top-1 size-6 text-muted-foreground hover:bg-background hover:text-foreground"
          aria-label={state.copied ? t("update.copied") : t("update.copy")} disabled={state.busy || state.copied} onClick={() => void copyPrompt()}>
          {state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        </Button>
      </TooltipHint>
    </div>
    {state.message ? <p className="text-xs text-muted-foreground" role="status">{state.message}</p> : null}
    <div className="flex justify-end">
      <Button size="xs" className="font-medium" disabled={state.busy || (!sends && state.copied)}
        onClick={() => void (sends ? sendPrompt() : copyPrompt())}>
        {sends ? <ArrowUp aria-hidden="true" /> : state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {sends ? t("update.sendToAgent") : state.copied ? t("update.copied") : t("update.copyPrompt")}
      </Button>
    </div>
  </div>;
}
