// The two right-hand panels — the theme editor and the file sheet — and who
// owns whether each one is open (docs/file-view.md, "Driving the panels from
// a host").
//
// They are ONE panel with two contents: one width, one resize handle, one
// inset on the 3D viewport. So opening either closes the other, and that rule
// lives here rather than at each of the half-dozen places that opens one.
//
// A host may drive either panel by passing a boolean. That makes the panel
// controlled: the surface stops keeping its own flag for it and reports every
// change instead, so a host drawing its own toggle (the desktop app's file
// tab, which hides the surface's top bar) can highlight it. Pass nothing —
// the standalone viewer — and the surface owns both, exactly as before.
//
// A host that gives a callback but no value is OBSERVING: the surface still
// owns the flag and reports it, its opening value included, so a host can
// start from the surface's own default — a STEP file opens with its sheet up
// — without having to know what that default is. Echo the report back into
// the prop and the panel is controlled from then on.
//
// Plain functions in a module with no `@/` imports, so `node --test` can load
// them without the bundler's aliases.

export const HOST_PANEL = {
  THEME: "theme",
  FILE_SHEET: "fileSheet"
};

/**
 * True when a host is driving this panel. A boolean is a claim of ownership;
 * anything else — undefined, null, the default — leaves it to the surface.
 * Not truthiness: `false` is a host saying "closed", not a host saying
 * nothing.
 */
export function isHostPanelControlled(value) {
  return value === true || value === false;
}

/** The panel's open flag: the host's when it gives one, else the surface's own. */
export function resolveHostPanelOpen(hostValue, ownValue) {
  return isHostPanelControlled(hostValue) ? hostValue : ownValue === true;
}

/**
 * Both flags after opening, closing or flipping one of them.
 *
 * `open` omitted is the toggle a button press means. Flipping one WHILE THE
 * OTHER IS UP opens it rather than closing it: the two share a panel, so the
 * gesture reads as "show me this instead", and the panel never blinks shut
 * on the way.
 */
export function nextPanelState(current, panel, open) {
  const theme = current?.themeEditing === true;
  const sheet = current?.fileSheetOpen === true;
  const isTheme = panel === HOST_PANEL.THEME;
  const mine = isTheme ? theme : sheet;
  const other = isTheme ? sheet : theme;
  const next = isHostPanelControlled(open) ? open : other || !mine;
  return isTheme
    ? { themeEditing: next, fileSheetOpen: next ? false : sheet }
    : { themeEditing: next ? false : theme, fileSheetOpen: next };
}
