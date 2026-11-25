/**
 * A schematic's glyphs, on lucide's 24-unit grid and in the board's one line (1.7, round:
 * `../board/boardIcons.jsx`), outlines only, so each reads at the strip's 14px: the
 * kinds a pick names, in Quick Edit's chips and the panel's rows: a symbol (a resistor's zigzag body
 * with its leads), a pin (a lead with its end dot), a net (two pins and the wire between them, a label's
 * flag on it), a sheet (a sheet symbol, its pins' flags on its edge), a label (a flag), a wire (a bent
 * wire with a junction), a junction (a dot), a no-connect (a cross) and a bus entry (a slanted stub off a
 * thick bus).
 */
const icon = (name, children) => {
  function SchematicIcon(props) {
    return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" {...props}>{children}</svg>;
  }
  SchematicIcon.displayName = name;
  return SchematicIcon;
};

export const SymbolKindIcon = icon("SymbolKindIcon", <path d="M12 2.5v4l3 1.5-6 3 6 3-6 3 3 1.5v4" />);
export const PinKindIcon = icon("PinKindIcon", <><path d="M3.5 12h12" /><circle cx="18.5" cy="12" r="2.5" fill="currentColor" /></>);
export const NetKindIcon = icon("NetKindIcon", <><circle cx="4.5" cy="17.5" r="2" fill="currentColor" /><circle cx="19.5" cy="17.5" r="2" fill="currentColor" />
  <path d="M6.5 17.5h11M9 13.5V7.5h6l2 3-2 3H9" /></>);
export const SheetKindIcon = icon("SheetKindIcon", <><rect x="5" y="3.5" width="14" height="17" rx="1" /><path d="M5 9l2.5 1.5L5 12M19 13l-2.5 1.5L19 16" /></>);
export const LabelKindIcon = icon("LabelKindIcon", <path d="M3.5 8.5h12l4.5 3.5-4.5 3.5h-12Z" />);
export const WireKindIcon = icon("WireKindIcon", <><path d="M3 17.5h8.5V6.5H21" /><circle cx="11.5" cy="12" r="2" fill="currentColor" /></>);
export const JunctionKindIcon = icon("JunctionKindIcon", <><path d="M3 12h18M12 12v9" /><circle cx="12" cy="12" r="3" fill="currentColor" /></>);
export const NoConnectKindIcon = icon("NoConnectKindIcon", <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />);
export const BusEntryKindIcon = icon("BusEntryKindIcon", <><path d="M3 19h18" strokeWidth="3" /><path d="M8 19l6-6h7" /></>);
