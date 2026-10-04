import { ArrowUp, Check, Copy, X } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "../primitives/button.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import type { UpdateNotice } from "./useUpdateNotice.js";

/**
 * A newer text-to-cad, said once per release, with the prompt that has the person's agent update
 * it. Its buttons are Quick Edit's, each with its icon: where the host takes messages, Send to agent
 * (the send arrow) posts the prompt to the chat, with Copy prompt beside it as a secondary icon;
 * elsewhere, or when sending fails, Copy prompt is the one button, in words with its icon first.
 * Sending or copying it, or closing the card, is the person's answer (`onAnswer`, `onClose`).
 * Manual installation is the way round an agent that cannot do it: a real link to a new tab, which
 * `onLink` is how this host follows, and no answer, so the card stays. A host hands it to the viewer
 * as its `notice`, after the analytics card has been answered.
 */
export function UpdateCard({ notice, send, copy, onLink, onAnswer, onClose }: {
  notice: UpdateNotice;
  /** Posts the prompt to the chat, where the host can. */
  send?: (prompt: string) => Promise<void>;
  copy(prompt: string): Promise<void>;
  onLink(url: string): void;
  onAnswer(): void;
  onClose(): void;
}) {
  const id = useId();
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
      onAnswer();
      setState(previous => ({ unsent: previous.unsent, copied: true, message: "Copied. Paste it into your agent's chat." }));
    } catch {
      setState(previous => ({ unsent: previous.unsent, message: "It could not be copied. Select the prompt above and copy it." }));
    }
  };
  return <div className="flex flex-col gap-2 rounded-md border bg-popover p-3 text-ui text-popover-foreground shadow-md" role="dialog"
    aria-labelledby={`${id}-title`} aria-describedby={`${id}-text`}>
    <div className="flex items-center justify-between gap-2">
      <h2 id={`${id}-title`} className="font-medium">Update available</h2>
      <Button variant="ghost" size="icon-xs" className="-mr-1" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></Button>
    </div>
    <p id={`${id}-text`} className="text-xs text-muted-foreground">{notice.text}. Your agent can update it:</p>
    <p className="select-text rounded-sm bg-muted px-2 py-1 font-mono text-xs text-foreground">{notice.prompt}</p>
    {state.message ? <p className="text-xs text-muted-foreground" role="status">{state.message}</p> : null}
    <div className="flex items-center justify-between gap-2">
      <a href={notice.instructions} target="_blank" rel="noreferrer"
        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        onClick={event => { event.preventDefault(); onLink(notice.instructions); }}>Manual installation</a>
      <div className="flex items-center gap-1.5">
        {sends ? <TooltipHint content="Copy prompt" side="bottom">
          <Button variant="secondary" size="icon-xs" aria-label={state.copied ? "Prompt copied" : "Copy prompt"}
            disabled={state.busy || state.copied} onClick={() => void copyPrompt()}>
            {state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          </Button>
        </TooltipHint> : null}
        <Button size="xs" className="font-medium" disabled={state.busy || (!sends && state.copied)}
          onClick={() => void (sends ? sendPrompt() : copyPrompt())}>
          {sends ? <ArrowUp aria-hidden="true" /> : state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {sends ? "Send to agent" : state.copied ? "Copied" : "Copy prompt"}
        </Button>
      </div>
    </div>
  </div>;
}
