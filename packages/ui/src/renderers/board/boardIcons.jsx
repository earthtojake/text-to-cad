/**
 * A board's glyphs, on lucide's 24-unit grid and in the 3D Display modes' one line (1.7, round:
 * `kit/view-settings/DisplayModeOptions.js`), outlines only, so each still reads at the strip's
 * 14px: the kinds a pick names, in Quick Edit's chips and the Circuit's rows (a part with its legs; a pad;
 * a net, two pads and the trace between them; a track, a trace with its bend; a via, a ring round
 * its hole; a zone, a pour's outline with a corner cut, faintly filled; a rule area, the same
 * outline hatched, as KiCad draws a keepout; a text, a T; a dimension, a measured span between its
 * extension lines; a graphic, a square, a circle and a line), and an area a drag names, a point in
 * a dashed box.
 */
const icon = (name, children) => {
  function BoardIcon(props) {
    return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" {...props}>{children}</svg>;
  }
  BoardIcon.displayName = name;
  return BoardIcon;
};


export const PartKindIcon = icon("PartKindIcon", <><rect x="7" y="5" width="10" height="14" rx="1" /><path d="M3.5 8.5H7M3.5 12H7M3.5 15.5H7M17 8.5h3.5M17 12h3.5M17 15.5h3.5" /></>);
export const PadKindIcon = icon("PadKindIcon", <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" />);
export const NetKindIcon = icon("NetKindIcon", <><rect x="2.5" y="14.5" width="6" height="6" rx="1" fill="currentColor" /><rect x="15.5" y="3.5" width="6" height="6" rx="1" fill="currentColor" /><path d="M8.5 17.5H12l3.5-11" /></>);
export const TrackKindIcon = icon("TrackKindIcon", <path d="M3 17.5h6.5l5-11H21" strokeWidth="2.6" />);
export const ViaKindIcon = icon("ViaKindIcon", <><circle cx="12" cy="12" r="7.5" /><circle cx="12" cy="12" r="2.75" fill="currentColor" /></>);
export const ZoneKindIcon = icon("ZoneKindIcon", <path d="M3.5 5.5h12l5 5v8h-17Z" fill="currentColor" fillOpacity="0.3" />);
export const RuleAreaKindIcon = icon("RuleAreaKindIcon", <><path d="M3.5 5.5h12l5 5v8h-17Z" /><path d="M3.5 11.5l6-6M3.5 17.5l12-12M9.5 18.5l11-11M15.5 18.5l5-5" strokeWidth="1.2" /></>);
export const TextKindIcon = icon("TextKindIcon", <path d="M5.5 7.5v-2.5h13v2.5M12 5v14M9 19h6" />);
export const DimensionKindIcon = icon("DimensionKindIcon", <path d="M3.5 6v12M20.5 6v12M3.5 12h17M7 9l-3.5 3L7 15M17 9l3.5 3-3.5 3" />);
export const GraphicKindIcon = icon("GraphicKindIcon", <><rect x="3.5" y="3.5" width="7" height="7" rx="1" /><circle cx="16.75" cy="16.75" r="3.75" /><path d="M14 4l6.5 6.5" /></>);
export const AreaKindIcon = icon("AreaKindIcon", <><rect x="3.5" y="3.5" width="17" height="17" rx="1.5" strokeDasharray="3 2.6" /><circle cx="12" cy="12" r="2" fill="currentColor" /></>);
