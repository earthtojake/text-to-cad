import { useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";

/** Shared compact header/body for persistent tool controls, floating or anchored. */
export default function ToolPanel({ title, label, summary, collapsible = false, onClose, closeTitle = "Close", children }) {
  const [collapsed, setCollapsed] = useState(false);
  const buttonClass = "flex size-5 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
  return <>
    <div className="sticky top-0 z-10 flex min-h-7 items-center justify-end bg-popover pl-2 pr-1">
      {title ? <h3 className="mr-auto flex items-center gap-2 text-xs font-normal">{title}{summary ? <span className="text-tiny text-muted-foreground">{summary}</span> : null}</h3> : null}
      {collapsible ? <button type="button" aria-label={`${collapsed ? "Expand" : "Collapse"} ${label.toLowerCase()}`} aria-expanded={!collapsed}
        className={buttonClass} onClick={() => setCollapsed(value => !value)}>
        {collapsed ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      </button> : null}
      <button type="button" aria-label={`Close ${label.toLowerCase()}`} 
        className={buttonClass} onClick={onClose}><X className="size-3" aria-hidden="true" /></button>
    </div>
    {collapsible ? <div hidden={collapsed}>{children}</div> : children}
  </>;
}
