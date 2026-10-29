import { ArrowUp, Check, Copy, RefreshCw, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "../primitives/button.jsx";
import { Spinner } from "../primitives/spinner.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useI18n } from "../i18n/index.js";
import { readUpdateNotice, type UpdateNotice, type UpdateStart } from "./useUpdateNotice.js";

/** How often a card that started the engine's update reads the notice again while it runs. */
export const UPDATE_POLL_MS = 2000;

/**
 * A newer text-to-cad, and the one thing to do about it: what the update button (`UpdateButton`)
 * opens. For a copy the engine does not update, the install command, with a copy icon in its
 * top-right corner as a code block on GitHub has, and Quick Edit's button with its icon: where the
 * host takes messages, Send to agent (the send arrow) posts the prompt that has the agent run the
 * command; elsewhere, or when sending fails, Copy command. Where the engine updates itself
 * (`notice.auto`), the one thing to do is after a failure: the engine's error and Try again (the
 * host's `update`), whose run the card follows, reading the notice every two seconds until it lands
 * (the notice goes, and the button with it) or fails again. An installed update needs nothing: the
 * next thread, session or page runs it. Manual installation links to the install
 * instructions: a real link to a new tab, which `onLink` is how this host follows. Nothing here is
 * an answer to keep: the X closes the card, as a prompt sent does.
 */
export function UpdateCard({ id, notice, send, copy, onLink, onClose, update, onRun }: {
  /** The ids of its title and text (`${id}-title`, `${id}-text`), which label what holds it. */
  id: string;
  notice: UpdateNotice;
  /** Posts the prompt to the chat, where the host can. */
  send?: (prompt: string) => Promise<void>;
  /** Copies the command. */
  copy(text: string): Promise<void>;
  onLink(url: string): void;
  /** Closes the card: its X, and a prompt sent. */
  onClose(): void;
  /** Starts the engine's update again (Try again), where the host can. */
  update?: UpdateStart;
  /** Hears whether a run this card started is under way: what keeps the card shown meanwhile. */
  onRun?(running: boolean): void;
}) {
  const [state, setState] = useState<{ busy?: boolean; copied?: boolean; unsent?: boolean; message?: string }>({});
  // The engine's update this card started: the notice it started from, until another says it landed.
  const [run, setRun] = useState<{ from: UpdateNotice } | null>(null);
  const [act, setAct] = useState<{ busy?: boolean; reason?: string }>({});
  const { t } = useI18n();
  const auto = notice.auto;
  const onRunRef = useRef(onRun);
  onRunRef.current = onRun;
  useEffect(() => { onRunRef.current?.(run !== null); }, [run]);
  useEffect(() => {
    if (!run) return;
    const timer = setInterval(readUpdateNotice, UPDATE_POLL_MS);
    return () => clearInterval(timer);
  }, [run]);
  // A notice read since the run started that says it failed again, as the card then shows. One that
  // landed is no notice at all: the host drops the button, and the card with it.
  useEffect(() => {
    if (run && notice !== run.from && (!auto || auto.state === "failed")) setRun(null);
  }, [run, notice, auto]);
  // What a press said belongs to the state it was pressed in.
  useEffect(() => { setAct({}); }, [auto?.state]);

  const link = <a href={notice.instructions} target="_blank" rel="noreferrer"
    className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
    onClick={event => { event.preventDefault(); onLink(notice.instructions); }}>{t("update.manualInstallation")}</a>;
  const reason = act.reason ? <p className="text-xs text-muted-foreground" role="status">{act.reason}</p> : null;
  const card = (title: string, body: ReactNode) => <div className="flex flex-col gap-2 rounded-md border bg-popover p-3 text-ui text-popover-foreground shadow-md" data-update-card="">
    <div className="flex items-center justify-between gap-2">
      <h2 id={`${id}-title`} className="font-medium">{title}</h2>
      <Button variant="ghost" size="icon-xs" className="-mr-1" aria-label={t("update.close")} onClick={onClose}><X aria-hidden="true" /></Button>
    </div>
    {body}
  </div>;
  const text = (words: string) => <p id={`${id}-text`} className="text-xs text-muted-foreground">{words}</p>;

  if (auto && (run || auto.state === "updating")) {
    const release = auto.release;
    return card(t("update.updatingTitle"), <div className="flex items-center gap-2">
      <Spinner className="size-3.5 text-muted-foreground" aria-hidden="true" role={undefined} />
      {text(t(auto.state === "updating" && auto.stage === "installing" ? "update.installing" : "update.downloading", { release }))}
    </div>);
  }

  if (auto?.state === "failed") {
    const error = auto.error?.trim();
    const tryAgain = async () => {
      setAct({ busy: true });
      try {
        const reply = await update!();
        if (!reply.started) { setAct({ reason: reply.reason || t("update.notStarted") }); return; }
        setAct({});
        setRun({ from: notice });
      } catch {
        setAct({ reason: t("update.notStarted") });
      }
    };
    return card(t("update.failed"), <>
      {text(error || t("update.failedUnexplained", { release: auto.release }))}
      <div className="flex items-center justify-between gap-2">
        {link}
        {update ? <Button size="xs" className="font-medium" disabled={act.busy} onClick={() => void tryAgain()}>
          {act.busy ? <Spinner aria-hidden="true" role={undefined} /> : <RefreshCw aria-hidden="true" />}{t("update.tryAgain")}
        </Button> : null}
      </div>
      {reason}
    </>);
  }

  // A copy the engine does not update (or one whose update is still to come): the command.
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
  const copyCommand = async () => {
    setState(previous => ({ ...previous, busy: true }));
    try {
      await copy(notice.command);
      setState(previous => ({ unsent: previous.unsent, copied: true, message: t("update.copiedHint") }));
    } catch {
      setState(previous => ({ unsent: previous.unsent, message: t("update.copyFailed") }));
    }
  };
  return card(t("update.available"), <>
    {text(t("update.description"))}
    <div className="relative rounded-sm bg-muted" data-update-command="">
      <p className="select-text py-1 pl-2 pr-8 font-mono text-xs text-foreground [overflow-wrap:anywhere]">{notice.command}</p>
      <TooltipHint content={state.copied ? t("update.copied") : t("update.copy")} side="bottom">
        <Button variant="ghost" size="icon-xs" className="absolute right-1 top-1 size-6 text-muted-foreground hover:bg-background hover:text-foreground"
          aria-label={state.copied ? t("update.copied") : t("update.copy")} disabled={state.busy || state.copied} onClick={() => void copyCommand()}>
          {state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        </Button>
      </TooltipHint>
    </div>
    {state.message ? <p className="text-xs text-muted-foreground" role="status">{state.message}</p> : null}
    <div className="flex items-center justify-between gap-2">
      {link}
      <Button size="xs" className="font-medium" disabled={state.busy || (!sends && state.copied)}
        onClick={() => void (sends ? sendPrompt() : copyCommand())}>
        {sends ? <ArrowUp aria-hidden="true" /> : state.copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {sends ? t("update.sendToAgent") : state.copied ? t("update.copied") : t("update.copyCommand")}
      </Button>
    </div>
  </>);
}
