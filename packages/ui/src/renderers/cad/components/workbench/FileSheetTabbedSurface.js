import { useEffect, useState } from "react";
import { cn } from "@hardcore/ui/utils";
import { ScrollArea } from "@hardcore/ui/primitives/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@hardcore/ui/primitives/tabs";
import { resolveActiveFileSheetSectionId } from "../../workbench/fileSheetSections.js";

// Keep visited inspection trees mounted so tab switches retain disclosure and scroll state.
// Other sections retain their existing mount/unmount lifecycle.
function FileSheetTabContent({ section, active, hasTabs }) {
  const [visited, setVisited] = useState(active);
  useEffect(() => { if (active) setVisited(true); }, [active]);
  if (!active && (!section.keepMounted || !visited)) return null;
  const content = typeof section.content === "function" ? section.content(active) : section.content;
  return <TabsContent value={section.id} forceMount hidden={!active} {...(!hasTabs && { role: "region", "aria-label": section.title, "aria-labelledby": undefined })} className={cn("min-h-0 flex-1 overflow-hidden", active && "flex flex-col")} data-file-sheet-tab-panel={section.id}>
    {section.scrollsContent ? content : <ScrollArea className="min-h-0 flex-1" viewportClassName="h-full">{content}</ScrollArea>}
  </TabsContent>;
}

// Descriptor order is the canonical order for each format. Only the active tab
// belongs to per-file state; old global drag/split preferences are never read.
export default function FileSheetTabbedSurface({ sections, openSectionIds = [], onOpenSectionIdsChange }) {
  const visibleSections = Array.isArray(sections) ? sections.filter(Boolean) : [];
  const sectionIds = visibleSections.map(section => section.id);
  const activeId = resolveActiveFileSheetSectionId(openSectionIds, sectionIds);
  const hasTabs = visibleSections.length > 1;

  return (
    <Tabs value={activeId} onValueChange={id => onOpenSectionIdsChange?.([id])}
      className="min-h-0 min-w-0 flex-1 gap-0">
      {hasTabs && <TabsList aria-label="Model panels"
        className="mx-2 my-2 max-w-[calc(100%-1rem)] shrink-0 justify-start overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {visibleSections.map(section => <TabsTrigger key={section.id} value={section.id}
          title={section.titleAttr || undefined} data-file-sheet-tab={section.id}
          className="max-w-[12rem] flex-none select-none">
          <span className="min-w-0 truncate text-sm">{section.title}</span>
        </TabsTrigger>)}
      </TabsList>}
      {visibleSections.map(section => <FileSheetTabContent key={section.id}
        section={section} active={section.id === activeId} hasTabs={hasTabs} />)}
    </Tabs>
  );
}
