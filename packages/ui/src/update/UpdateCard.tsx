import { ArrowUp, Check, Copy, X } from "lucide-react";
import { useState } from "react";
import { Button } from "../primitives/button.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useI18n } from "../i18n/index.js";
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
  const { t } = useI18n();
  const sends = Boolean(send) && !state.unsent;
  const sendPrompt = async () => {
    setState(previous => ({ ...previous, busy: true }));
    try {
      await send!(notice.prompt);
      onClose();
    } catch {
      setState({ unsent: true, message: t("update.sendFailed") });
    }
  };
  const copyPrompt = async () => {
    setState(previous => ({ ...previous, busy: true }));
    try {
      await copy(notice.prompt);
      setState(previous => ({ unsent: previous.unsent, copied: true, message: t("update.copiedHint") }));
    } catch {
      setState(previous => ({ unsent: previous.unsent, message: t("update.copyFailed") }));
    }
  };
  return <div className="flex flex-col gap-2 rounded-md border bg-popover p-3 text-ui text-popover-foreground shadow-md" data-update-card="">
    <div className="flex items-center justify-between gap-2">
      <h2 id={`${id}-title`} className="font-medium">{t("update.available")}</h2>
      <Button variant="ghost" size="icon-xs" className="-mr-1" aria-label={t("update.close")} onClick={onClose}><X aria-hidden="true" /></Button>
    </div>
    <p id={`${id}-text`} className="text-xs text-muted-foreground">{t("update.description")}</p>
    <div className="relative rounded-sm bg-muted" data-update-prompt="">
      <p className="select-text py-1 pl-2 pr-8 font-mono text-xs text-foreground">{notice.prompt}</p>
      <TooltipHint content={state.copied ? t("update.copied") : t("update.copy")} side="bottom">
        <Button variant="ghost" size="icon-xs" className="absolute right-1 top-1 size-6 text-muted-foreground hover:bg-background hover:text-foreground"
          aria-label={state.copied ? t("update.copied") : t("update.copy")} disabled={state.busy || state.copied} onClick={() => void copyPrompt()}>
          {state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        </Button>
      </TooltipHint>
    </div>
    {state.message ? <p className="text-xs text-muted-foreground" role="status">{state.message}</p> : null}
    <div className="flex items-center justify-between gap-2">
      <a href={notice.instructions} target="_blank" rel="noreferrer"
        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        onClick={event => { event.preventDefault(); onLink(notice.instructions); }}>{t("update.manualInstallation")}</a>
      <Button size="xs" className="font-medium" disabled={state.busy || (!sends && state.copied)}
        onClick={() => void (sends ? sendPrompt() : copyPrompt())}>
        {sends ? <ArrowUp aria-hidden="true" /> : state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {sends ? t("update.sendToAgent") : state.copied ? t("update.copied") : t("update.copyPrompt")}
      </Button>
    </div>
  </div>;
}
