import { useEffect, useMemo, useRef } from "react";
import { Box } from "lucide-react";
import { cn } from "@/ui/utils";
import { Button } from "../ui/button";
import { FileSheetSubsection } from "./FileSheet";

function ComponentRow({ component, selected, onSelect, onHover }) {
  const rowRef = useRef(null);
  useEffect(() => {
    if (selected) rowRef.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  return (
    <Button
      ref={rowRef}
      type="button"
      variant="ghost"
      aria-pressed={selected}
      title={component.name}
      className={cn("h-7 w-full justify-start gap-2 rounded-none px-2 text-xs font-normal", selected && "bg-accent text-accent-foreground")}
      onClick={(event) => onSelect(component.id, { multiSelect: event.ctrlKey || event.metaKey || event.shiftKey })}
      onMouseEnter={() => onHover(component.id)}
      onMouseLeave={() => onHover("")}
      onFocus={() => onHover(component.id)}
      onBlur={() => onHover("")}
    >
      <Box className="size-3.5 shrink-0" aria-hidden="true" />
      <span className="truncate">{component.name}</span>
    </Button>
  );
}

export default function RobotComponentsSection({ components, selectedIds, onSelect, onHover }) {
  const groups = useMemo(() => Object.groupBy(components, (component) => component.linkName), [components]);
  return Object.entries(groups).map(([linkName, entries]) => (
    <FileSheetSubsection key={linkName} title={linkName} contentClassName="space-y-0">
      {entries.map((component) => (
        <ComponentRow key={component.id} component={component} selected={selectedIds.includes(component.id)} onSelect={onSelect} onHover={onHover} />
      ))}
    </FileSheetSubsection>
  ));
}
