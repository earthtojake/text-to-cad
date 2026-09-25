import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@hardcore/ui/primitives/tabs";
import FilePanelSections from "./FilePanelSections.jsx";

/** Separate navigation and positioning without nesting scroll areas. Keep both
 * mounted so switching tabs preserves tree disclosure, selection and scroll. */
export default function FilePanelTabs({ sections, active, revealRequest }) {
  const shown = sections.filter(Boolean);
  const model = shown.find(section => section.id === "features" || section.id === "links");
  const position = shown.find(section => section.id === "position");
  // A reveal turns the tab in the same render as the press that asked for it: adjusted while
  // rendering, not in an effect, which would paint the old tab for a frame first.
  const revealed = request => (request?.sectionId === "position" ? "position" : model?.id);
  const [selected, setSelected] = useState(() => revealed(revealRequest));
  const [seenRequest, setSeenRequest] = useState(revealRequest);
  if (revealRequest !== seenRequest) {
    setSeenRequest(revealRequest);
    if (revealRequest) setSelected(revealed(revealRequest));
  }
  if (!model || !position) return <FilePanelSections sections={sections} active={active} revealRequest={revealRequest} />;
  const current = selected === "position" ? "position" : model.id;
  const groups = [
    { ...model, sections: shown.filter(section => section.id !== "position") },
    { ...position, sections: [position] },
  ];
  return <Tabs value={current} onValueChange={setSelected} className="min-h-0 flex-1 gap-0">
    <div data-mobile-panel-top-row="" className="shrink-0 px-2 pt-2"><TabsList className="h-7 p-0.5">
      {groups.map(group => <TabsTrigger key={group.id} value={group.id} className="px-2 py-0.5 text-tiny">{group.title}</TabsTrigger>)}
    </TabsList></div>
    {groups.map(group => <TabsContent key={group.id} value={group.id} forceMount hidden={current !== group.id}
      className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden">
      <FilePanelSections active={active && current === group.id} sticky={false}
        sections={group.sections.map(section => ({ ...section, collapsible: false, hideHeading: section.id === group.id }))} />
    </TabsContent>)}
  </Tabs>;
}
