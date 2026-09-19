import { cn } from "@hardcore/ui/utils";
import { X } from "lucide-react";

export const CAD_WORKSPACE_TOOLBAR_DESKTOP_WIDTH_CLASS = "w-[min(15rem,calc(100vw-2rem))]";
export const TOOLBAR_MENU_ROW_CLASS = "flex w-full cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground disabled:pointer-events-none disabled:opacity-50";

export default function ToolbarShell({ className, children, title, label = title, onClose, closeLabel, footer }) {
  return (
    <section
      aria-label={label}
      className={cn(
        "pointer-events-auto flex min-h-0 w-60 max-w-full flex-col overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md",
        className
      )}
    >
      {title && <>
        <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm font-medium">
          <span>{title}</span>
          {onClose && <button type="button" className="rounded-sm p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={closeLabel || `Close ${title}`} onClick={onClose}><X className="size-3" aria-hidden="true" /></button>}
        </div>
        <div className="-mx-1 my-1 h-px shrink-0 bg-border" />
      </>}
      <div className="shrink-0">{children}</div>
      {footer && <><div className="-mx-1 my-1 h-px shrink-0 bg-border" /><p className="px-2 py-1.5 text-micro text-muted-foreground">{footer}</p></>}
    </section>
  );
}
