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
export default function FileSheetTabbedSurface({ sections, openSectionIds = [], onOpenSectionIdsChange, headerActions = null }) {
  const visibleSections = Array.isArray(sections) ? sections.filter(Boolean) : [];
  const sectionIds = visibleSections.map(section => section.id);
  const activeId = resolveActiveFileSheetSectionId(openSectionIds, sectionIds);
  const hasTabs = visibleSections.length > 1;

  return (
    <Tabs value={activeId} onValueChange={id => onOpenSectionIdsChange?.([id])}
      className="min-h-0 min-w-0 flex-1 gap-0">
      {visibleSections.length > 0 && <div className="mx-2 mt-2 mb-1 flex min-w-0 shrink-0 items-center gap-1" data-file-sheet-header>
      {/* One section needs no strip to choose from, but the Inspector still says what it is showing:
          its title, in the metrics of the tab it would have been. */}
      {!hasTabs && <h2 className="flex h-7 min-w-0 items-center truncate px-2 text-sm font-normal" data-file-sheet-title>{visibleSections[0].title}</h2>}
      {hasTabs && <TabsList aria-label="Inspector panels"
        className="h-7 p-0.5 shrink-0 justify-start">
        {visibleSections.map(section => <TabsTrigger key={section.id} value={section.id}
          title={section.titleAttr || undefined} data-file-sheet-tab={section.id}
          className="h-6 max-w-[12rem] flex-none select-none px-1.5 py-0 leading-none">
          <span className="min-w-0 truncate text-sm">{section.title}</span>
        </TabsTrigger>)}
      </TabsList>}
      {headerActions && <div className="ml-auto shrink-0">{headerActions}</div>}
      </div>}
      {visibleSections.map(section => <FileSheetTabContent key={section.id}
        section={section} active={section.id === activeId} hasTabs={hasTabs} />)}
    </Tabs>
  );
}
