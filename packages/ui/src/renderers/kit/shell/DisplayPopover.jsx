import { useViewerHost } from "../../../host/context.js";
import { SettingsPopover } from "./SettingsPopover.jsx";

/**
 * A file's Settings: the settings cog among the view's controls in the navbar, before Preview,
 * opening down from it, end-aligned (`SettingsPopover`), over the Display settings (`children`),
 * whose own heading keeps its Reset, and the host's own settings after them. It is not a tool —
 * opening it leaves the tool in hand as it is — and a press on the model closes it too.
 * @param {{ open: boolean, onOpenChange(open: boolean): void, disabled?: boolean, children: import("react").ReactNode }} props
 *   `children`: the Display sections (`useRendererShell`'s `frame.display`).
 */
export default function DisplayPopover({ open, onOpenChange, disabled = false, children }) {
  const { links } = useViewerHost();
  return <SettingsPopover links={links} open={open} onOpenChange={onOpenChange} disabled={disabled}>{children}</SettingsPopover>;
}
