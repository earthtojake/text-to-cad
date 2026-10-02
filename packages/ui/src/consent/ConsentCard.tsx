import { X } from "lucide-react";
import { Button } from "../primitives/button.jsx";

/**
 * The one question a CAD app asks, once, of everyone who runs it: whether to share anonymous usage
 * statistics. Nothing is sent before a yes, and any answer ends the question (closing it is No
 * thanks); Settings' Analytics section changes it later. It keeps to the top-right corner: the
 * home's (`placement: "home"`, which has no navbar), and a viewer's under its navbar. The privacy
 * policy is a real link to a new tab; `onPolicy` is how this host follows one.
 */
export function ConsentCard({ placement, policy, onAnswer, onPolicy }: {
  placement: "home" | "viewer";
  policy: string;
  onAnswer(share: boolean): void;
  onPolicy(url: string): void;
}) {
  const corner = placement === "home" ? "right-3 top-3" : "right-3 top-12";
  return <div className={`absolute z-50 w-[calc(100%-1.5rem)] max-w-xs ${corner}`} data-placement={placement}>
    <div className="flex flex-col gap-2 rounded-md border bg-popover p-3 text-ui text-popover-foreground shadow-md" role="dialog" aria-labelledby="cad-consent-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="cad-consent-title" className="font-medium">Allow Analytics</h2>
        {/* Closing is an answer, No thanks: the card never comes back to ask again. */}
        <Button variant="ghost" size="icon-xs" className="-mr-1" aria-label="Close and don't share" onClick={() => onAnswer(false)}><X aria-hidden="true" /></Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Help improve text-to-cad by sending anonymous usage statistics. We never collect your files, models or
        prompts. Read our{" "}
        <a href={policy} target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-2"
          onClick={event => { event.preventDefault(); onPolicy(policy); }}>Privacy Policy</a>.
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="xs" className="font-medium" onClick={() => onAnswer(false)}>No thanks</Button>
        <Button size="xs" className="font-medium" onClick={() => onAnswer(true)}>Allow</Button>
      </div>
    </div>
  </div>;
}
