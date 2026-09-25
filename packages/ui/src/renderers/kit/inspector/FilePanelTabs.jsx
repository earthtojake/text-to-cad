import { Tabs, TabsContent, TabsList, TabsTrigger } from "@hardcore/ui/primitives/tabs";
import FilePanelSections from "./FilePanelSections.jsx";

/** Separate navigation and positioning without nesting scroll areas. Keep both
 * mounted so switching tabs preserves tree disclosure, selection and scroll.
 *
 * The tabs come from what each section SAYS it is, never from its id: the section whose
 * `role` is "model" (the file's tree) heads the first tab, with every other section under
 * it, and the one whose `role` is "position" is the second. A panel without both is one
 * column of sections. `selected` is a section id, the owner's. */
export default function FilePanelTabs({ sections, active, revealRequest, selected = "", onSelectedChange }) {
  const shown = sections.filter(Boolean);
  const model = shown.find(section => section.role === "model");
  const position = shown.find(section => section.role === "position");
  // The selected tab is its owner's (the shell's), so it survives this component remounting;
  // a reveal sets it in the same press that asks for it, so the old tab never paints first.
  if (!model || !position) return <FilePanelSections sections={sections} active={active} revealRequest={revealRequest} />;
  const current = selected === position.id ? position.id : model.id;
  const groups = [
    { ...model, sections: shown.filter(section => section !== position) },
    { ...position, sections: [position] },
  ];
  return <Tabs value={current} onValueChange={onSelectedChange} className="min-h-0 flex-1 gap-0">
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
