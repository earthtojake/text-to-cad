import { Eye, EyeOff } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";
import { FileSheetSectionBody, FileSheetStatusText } from "../../kit/inspector/FileSheet.js";

/**
 * The Layers tab — the drawing analogue of STEP's Tree. A DXF's layers ARE its structure
 * (cut profile, bend creases, engravings, notes), so they get a tab of rows rather than a
 * settings subsection: name on the left, what the layer holds in the middle, and the same
 * hover-revealed eye the model tree uses on the right.
 */
const LAYER_KIND_LABELS = Object.freeze({ cut: "Cut", bend: "Bend", engrave: "Engrave", reference: "Reference" });

function layerFactsLabel(layer) {
  const kind = LAYER_KIND_LABELS[String(layer?.kind || "").toLowerCase()] || "Cut";
  const count = (Number(layer?.pathCount) || 0) + (Number(layer?.circleCount) || 0) + (Number(layer?.textCount) || 0);
  return count > 0 ? `${kind} · ${count}` : kind;
}

export function LayersTab({ layers = [], hiddenLayers = [], onLayerVisibilityChange }) {
  const hidden = new Set(Array.isArray(hiddenLayers) ? hiddenLayers : []);
  if (!layers.length) {
    return (
      <FileSheetSectionBody>
        <FileSheetStatusText className="py-1">No layers in this drawing.</FileSheetStatusText>
      </FileSheetSectionBody>
    );
  }
  return (
    <div className="max-w-full select-none space-y-px overflow-hidden pb-2">
      {layers.map((layer) => {
        const isHidden = hidden.has(layer.name);
        return (
          <div
            key={layer.name}
            className={cn(
              "group/layer-row flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-tiny",
              "hover:bg-sidebar-accent/60",
              isHidden && "opacity-60"
            )}
          >
            <span className="min-w-0 flex-1 truncate text-sidebar-foreground">{layer.name}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">{layerFactsLabel(layer)}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className={cn(
                "ml-1 size-6 shrink-0 text-muted-foreground hover:text-foreground",
                !isHidden && "opacity-0 group-hover/layer-row:opacity-100 focus-visible:opacity-100"
              )}
              aria-label={isHidden ? `Show layer ${layer.name}` : `Hide layer ${layer.name}`}
              title={isHidden ? "Show" : "Hide"}
              onClick={() => onLayerVisibilityChange?.(layer.name, /* nextVisible */ isHidden)}
            >
              {isHidden
                ? <Eye className="size-3" strokeWidth={1.8} aria-hidden="true" />
                : <EyeOff className="size-3" strokeWidth={1.8} aria-hidden="true" />}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
