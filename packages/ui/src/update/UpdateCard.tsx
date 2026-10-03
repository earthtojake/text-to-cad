import { X } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "../primitives/button.jsx";
import type { UpdateNotice } from "./useUpdateNotice.js";

/**
 * A newer text-to-cad, said once per release, with the prompt that has the person's agent update
 * it. Where the host takes messages, Send to agent posts the prompt to the chat; elsewhere, or when
 * sending fails, Copy prompt copies it for the person to paste. Sending or copying it, or closing the
 * card, is the person's answer (`onAnswer`, `onClose`). A host hands it to the viewer as its
 * `notice`, after the analytics card has been answered.
 */
export function UpdateCard({ notice, send, copy, onAnswer, onClose }: {
  notice: UpdateNotice;
  /** Posts the prompt to the chat, where the host can. */
  send?: (prompt: string) => Promise<void>;
  copy(prompt: string): Promise<void>;
  onAnswer(): void;
  onClose(): void;
}) {
  const id = useId();
  const [state, setState] = useState<{ busy?: boolean; copied?: boolean; unsent?: boolean; message?: string }>({});
  const sends = Boolean(send) && !state.unsent;
  const act = async () => {
    setState(previous => ({ ...previous, busy: true }));
    if (sends) {
      try {
        await send!(notice.prompt);
        onClose();
      } catch {
        setState({ unsent: true, message: "It could not be sent to the chat. Copy the prompt instead." });
      }
      return;
    }
    try {
      await copy(notice.prompt);
      onAnswer();
      setState({ unsent: state.unsent, copied: true, message: "Copied. Paste it into your agent's chat." });
    } catch {
      setState({ unsent: state.unsent, message: "It could not be copied. Select the prompt above and copy it." });
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
    <div className="flex justify-end">
      <Button size="xs" className="font-medium" disabled={state.busy || state.copied} onClick={() => void act()}>
        {sends ? "Send to agent" : state.copied ? "Copied" : "Copy prompt"}
      </Button>
    </div>
  </div>;
}
