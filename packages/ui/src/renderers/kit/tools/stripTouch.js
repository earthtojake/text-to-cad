import { createContext, useContext } from "react";

// Every size here is THE scale's (`globals.css`): a phone's is the same class at the phone's tokens.
// A floating toolbar's small tiles: the icon button (24px), their icons the small glyph (14px), whatever size the icon
// was handed at. No toolbar draws them now (the tools view has no playbar; the corner's zoom is `ZoomControl.jsx`'s own).
export const STRIP_BUTTON_CLASS = "size-icon-button [&>svg]:size-glyph-sm!";
// The tool strip at the view's top, Figma's toolbar's proportions at a 28px tile: the bar 40px tall with its 1px
// border, (40 - 2 - 28) / 2 = 5px in (`TOP_STRIP_SHAPE_CLASS`); a tile's corners 5/32 of it (4px), the bar's its
// padding and a tile's corner and 1 (10px), so the two curves run parallel; its icons 16px; a tool's menu chevron
// half a tile wide, its own 14x28 target touching its button (`ToolModeMenu.jsx`). The view's controls where they end
// it (Display and Preview, where no navbar holds them: `useStripButtonClass`), the model's effects (a renderer's strip tools of its own) and
// Animation's Play are its tiles too; the panel's head buttons are its tile's size (`FlatPanel.jsx`).
export const TOP_STRIP_BUTTON_CLASS = "size-control rounded-control [&>svg]:size-glyph!";
export const TOP_STRIP_SHAPE_CLASS = "items-center gap-step rounded-[calc(var(--cad-radius-control)+6px)] p-[5px]";
/** A phone's strip tile: the same tile, at a phone's tokens (kept as a name for the touch strip's layout). */
export const TOUCH_STRIP_BUTTON_CLASS = TOP_STRIP_BUTTON_CLASS;
// A small toolbar's shape around its tiles: 4px in, its tiles 4px apart, its corners rounded-md. No toolbar draws it
// now: the strip is `TOP_STRIP_SHAPE_CLASS`'s, the corner's zoom `ZoomControl.jsx`'s own.
export const STRIP_SHAPE_CLASS = "items-center gap-1 rounded-md p-1";

const StripTouch = createContext(false);
/** Marks the chrome over a phone's view, the strip and the rows under it, as touch-sized. */
export const StripTouchProvider = StripTouch.Provider;
/** Whether the strip in hand is a phone's: its tiles and chevrons are touch-sized. */
export const useStripTouch = () => useContext(StripTouch);
/** The class of a tile of the strip in hand: one, the scale sizing it on a phone. */
export const useStripButtonClass = () => TOP_STRIP_BUTTON_CLASS;
