import { ArrowUp, Check, Copy, X } from "lucide-react";
import { useState } from "react";
import { Button } from "../primitives/button.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import type { UpdateNotice } from "./useUpdateNotice.js";

/**
 * A newer text-to-cad, with the prompt that has the person's agent update it: what the update button
 * (`UpdateButton`) opens. The prompt has a copy icon in its top-right corner, as a code block on
 * GitHub does. Its button is Quick Edit's, with its icon: where the host takes messages, Send to
 * agent (the send arrow) posts the prompt to the chat; elsewhere, or when sending fails, Copy prompt,
 * in words with its icon first. Manual installation is the way round
 * an agent that cannot do it: a real link to a new tab, which `onLink` is how this host follows.
 * Nothing here is an answer to keep: the X closes the card, as a prompt sent does, and the button
 * stays until the update lands.
 */
export function UpdateCard({ id, notice, send, copy, onLink, onClose }: {
  /** The ids of its title and text (`${id}-title`, `${id}-text`), which label what holds it. */
  id: string;
  notice: UpdateNotice;
  /** Posts the prompt to the chat, where the host can. */
  send?: (prompt: string) => Promise<void>;
  copy(prompt: string): Promise<void>;
  onLink(url: string): void;
  /** Closes the card: its X, and a prompt sent. */
  onClose(): void;
}) {
  const [state, setState] = useState<{ busy?: boolean; copied?: boolean; unsent?: boolean; message?: string }>({});
  const sends = Boolean(send) && !state.unsent;
  const sendPrompt = async () => {
    setState(previous => ({ ...previous, busy: true }));
    try {
      await send!(notice.prompt);
      onClose();
    } catch {
      setState({ unsent: true, message: "It could not be sent to the chat. Copy the prompt instead." });
    }
  };
  const copyPrompt = async () => {
    setState(previous => ({ ...previous, busy: true }));
    try {
      await copy(notice.prompt);
      setState(previous => ({ unsent: previous.unsent, copied: true, message: "Copied. Paste it into your agent's chat." }));
    } catch {
      setState(previous => ({ unsent: previous.unsent, message: "It could not be copied. Select the prompt above and copy it." }));
    }
  };
  return <div className="flex flex-col gap-2 rounded-md border bg-popover p-3 text-ui text-popover-foreground shadow-md" data-update-card="">
    <div className="flex items-center justify-between gap-2">
      <h2 id={`${id}-title`} className="font-medium">Update available</h2>
      <Button variant="ghost" size="icon-xs" className="-mr-1" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></Button>
    </div>
    <p id={`${id}-text`} className="text-xs text-muted-foreground">A new version of text-to-cad is available. Send a message to your agent asking it to update to the latest version:</p>
    <div className="relative rounded-sm bg-muted" data-update-prompt="">
      <p className="select-text py-1 pl-2 pr-8 font-mono text-xs text-foreground">{notice.prompt}</p>
      <TooltipHint content={state.copied ? "Copied" : "Copy"} side="bottom">
        <Button variant="ghost" size="icon-xs" className="absolute right-1 top-1 size-6 text-muted-foreground hover:bg-background hover:text-foreground"
          aria-label={state.copied ? "Copied" : "Copy"} disabled={state.busy || state.copied} onClick={() => void copyPrompt()}>
          {state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        </Button>
      </TooltipHint>
    </div>
    {state.message ? <p className="text-xs text-muted-foreground" role="status">{state.message}</p> : null}
    <div className="flex items-center justify-between gap-2">
      <a href={notice.instructions} target="_blank" rel="noreferrer"
        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        onClick={event => { event.preventDefault(); onLink(notice.instructions); }}>Manual installation</a>
      <Button size="xs" className="font-medium" disabled={state.busy || (!sends && state.copied)}
        onClick={() => void (sends ? sendPrompt() : copyPrompt())}>
        {sends ? <ArrowUp aria-hidden="true" /> : state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {sends ? "Send to agent" : state.copied ? "Copied" : "Copy prompt"}
      </Button>
    </div>
  </div>;
}
