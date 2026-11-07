import { Fragment } from "react";
import { Button } from "../primitives/button.jsx";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../primitives/dialog.jsx";
import { useI18n } from "../i18n/index.js";
import { whatsNewNotes } from "./notes.js";

/** A body's words, a span in backticks set as code. */
function withCode(text: string) {
  return text.split("`").map((part, index) => index % 2
    ? <code key={index} className="font-mono">{part}</code>
    : <Fragment key={index}>{part}</Fragment>);
}

/**
 * What's new: the stock Dialog, the release's title and its items -- each a bold title and a sentence
 * or two -- and one primary button, Got it. Every way it closes (the button, Escape, a press outside)
 * is `onDismiss`; nothing else is offered. `entry` is the release (`useWhatsNew`), null for none.
 */
export function WhatsNewDialog({ entry, onDismiss }: { entry: string | null; onDismiss(): void }) {
  const { t } = useI18n();
  const notes = entry ? whatsNewNotes(entry, t) : null;
  return <Dialog open={Boolean(notes)} onOpenChange={open => { if (!open) onDismiss(); }}>
    {notes ? <DialogContent data-whats-new={entry}>
      <DialogHeader>
        <DialogTitle>{notes.title}</DialogTitle>
      </DialogHeader>
      <DialogDescription asChild>
        <ul className="flex flex-col gap-3 leading-5">
          {notes.items.map(item => <li key={item.id}>
            <strong className="font-semibold text-foreground">{item.title}</strong> {withCode(item.body)}
          </li>)}
        </ul>
      </DialogDescription>
      <DialogFooter>
        <DialogClose asChild><Button size="sm">{t("whatsNew.gotIt")}</Button></DialogClose>
      </DialogFooter>
    </DialogContent> : null}
  </Dialog>;
}
