/**
 * A board's glyphs, on lucide's 24-unit grid and in the 3D Display modes' one line (1.7, round:
 * `kit/view-settings/DisplayModeOptions.js`), outlines only, so each still reads at the strip's
 * 14px: the Display modes, each what the mode shows — Board, the outline with a part on it and a
 * trace from it to a pad; Copper, two pads joined by a trace through a via, nothing else;
 * Assembly, a part's body and legs in its dashed courtyard, its reference over it; Placement, two
 * parts and the straight airwire between them — and Select's kinds (a part with its legs; a pad;
 * a net, two pads and the trace between them).
 */
const icon = (name, children) => {
  function BoardIcon(props) {
    return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" {...props}>{children}</svg>;
  }
  BoardIcon.displayName = name;
  return BoardIcon;
};

export const BoardModeIcon = icon("BoardModeIcon", <><rect x="3" y="4" width="18" height="16" rx="2.5" />
  <rect x="6" y="8" width="5.5" height="8" rx="0.8" /><path d="M11.5 12h2.5l2.5-2.5" /><circle cx="17.75" cy="8.25" r="1.75" /></>);
export const CopperModeIcon = icon("CopperModeIcon", <><rect x="3" y="14" width="6" height="6" rx="1" /><rect x="15" y="4" width="6" height="6" rx="1" />
  <circle cx="17" cy="17" r="2.5" /><path d="M9 17h5.5M17 10v4.5" /></>);
export const AssemblyModeIcon = icon("AssemblyModeIcon", <><rect x="3" y="3" width="18" height="18" rx="2" strokeDasharray="2.5 2.5" />
  <rect x="8.5" y="10" width="7" height="7.5" rx="1" /><path d="M6.5 12h2M6.5 15.5h2M15.5 12h2M15.5 15.5h2M8.5 6.5h4" /></>);
export const PlacementModeIcon = icon("PlacementModeIcon", <><rect x="2.5" y="15" width="7" height="5" rx="1" /><rect x="14.5" y="4" width="7" height="5" rx="1" />
  <path d="M9.5 15l5-6" strokeDasharray="2 2" /></>);

export const PartKindIcon = icon("PartKindIcon", <><rect x="7" y="5" width="10" height="14" rx="1" /><path d="M3.5 8.5H7M3.5 12H7M3.5 15.5H7M17 8.5h3.5M17 12h3.5M17 15.5h3.5" /></>);
export const PadKindIcon = icon("PadKindIcon", <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" />);
export const NetKindIcon = icon("NetKindIcon", <><rect x="2.5" y="14.5" width="6" height="6" rx="1" fill="currentColor" /><rect x="15.5" y="3.5" width="6" height="6" rx="1" fill="currentColor" /><path d="M8.5 17.5H12l3.5-11" /></>);
