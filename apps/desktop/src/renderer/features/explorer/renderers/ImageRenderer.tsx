import { Maximize2, Minimize2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@renderer/components/ui/button";
import { cn } from "@renderer/lib/utils";

/**
 * An image on a checkerboard, so transparency is visible rather than being
 * mistaken for the pane's background — the one thing a person opening a `.png`
 * in a design or an icon directory is usually checking.
 *
 * Two sizes, because both are wanted and neither is right on its own: fit (the
 * whole picture) and 1:1 (the pixels). The default is fit, and the footer
 * always says the real dimensions.
 */
export function ImageRenderer({
  dataUrl,
  name,
  size,
}: {
  dataUrl: string;
  name: string;
  size: number;
}) {
  const [actual, setActual] = useState(false);
  const [dimensions, setDimensions] = useState<{ width: number; height: number } | null>(null);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className="relative min-h-0 flex-1 overflow-auto"
        style={{
          // A 16px checkerboard, built from two gradients rather than an asset
          // so it follows the theme and costs no request.
          backgroundImage:
            "linear-gradient(45deg, var(--muted) 25%, transparent 25%, transparent 75%, var(--muted) 75%), linear-gradient(45deg, var(--muted) 25%, transparent 25%, transparent 75%, var(--muted) 75%)",
          backgroundSize: "16px 16px",
          backgroundPosition: "0 0, 8px 8px",
        }}
      >
        <div className={cn("flex min-h-full min-w-full items-center justify-center p-6")}>
          <img
            alt={name}
            className={cn(
              "rounded-sm shadow-sm",
              actual ? "max-w-none" : "max-h-full max-w-full object-contain",
            )}
            onLoad={(event) =>
              setDimensions({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              })
            }
            src={dataUrl}
          />
        </div>
      </div>

      <div className="flex h-8 shrink-0 items-center justify-between border-t px-3 text-[11px] text-muted-foreground">
        <span>
          {dimensions ? `${dimensions.width} × ${dimensions.height}` : "—"} · {formatBytes(size)}
        </span>
        <Button
          className="h-6 gap-1.5 px-2 text-[11px]"
          onClick={() => setActual((current) => !current)}
          size="sm"
          variant="ghost"
        >
          {actual ? <Minimize2 className="size-3" /> : <Maximize2 className="size-3" />}
          {actual ? "Fit" : "Actual size"}
        </Button>
      </div>
    </div>
  );
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}
