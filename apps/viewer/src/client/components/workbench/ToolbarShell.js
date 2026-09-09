import { cn } from "@/ui/utils";

export const CAD_WORKSPACE_TOOLBAR_DESKTOP_WIDTH_CLASS = "w-[min(15rem,calc(100vw-2rem))]";

export default function ToolbarShell({ className, children }) {
  return (
    <div
      className={cn(
        "bg-background pointer-events-auto flex min-h-0 flex-col overflow-hidden rounded-md border border-border text-foreground shadow-sm",
        className
      )}
    >
      {children}
    </div>
  );
}
