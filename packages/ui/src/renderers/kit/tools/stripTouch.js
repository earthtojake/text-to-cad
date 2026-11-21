import { createContext, useContext } from "react";

// A floating toolbar's tiles: 24px, their icons 14px (a little over half the tile), whatever size the icon
// was handed at — the tool in hand's row, the zoom pill, the playbar. On a touch strip (a phone) they are
// 36px, their icons 18px.
export const STRIP_BUTTON_CLASS = "size-6 [&>svg]:size-3.5!";
// The tool strip at the view's top, Figma's toolbar's proportions at a 28px tile: the bar 40px tall with its 1px
// border, (40 - 2 - 28) / 2 = 5px in (`TOP_STRIP_SHAPE_CLASS`); a tile's corners 5/32 of it (4px), the bar's its
// padding and a tile's corner and 1 (10px), so the two curves run parallel; its icons 16px; a tool's menu chevron
// half a tile wide, its own 14x28 target touching its button (`ToolModeMenu.jsx`). The view's controls on it
// (Preview; a board's Flip, 2D/3D and Display), the model's effects' tiles, the panel's head buttons and its pill
// are its tiles too (`useStripButtonClass`, `FlatPanel.jsx`).
export const TOP_STRIP_BUTTON_CLASS = "size-7 rounded-[4px] [&>svg]:size-4!";
export const TOP_STRIP_SHAPE_CLASS = "items-center gap-1 rounded-[10px] p-[5px]";
export const TOUCH_STRIP_BUTTON_CLASS = "size-9 rounded-md [&>svg]:size-4.5!";
// The strip's own shape around its tiles (`FloatingToolBar.js`): 4px in, its tiles 4px apart, its
// corners rounded-md. A toolbar of any length is this shape on its surface (the corner's zoom pill too).
export const STRIP_SHAPE_CLASS = "items-center gap-1 rounded-md p-1";

const StripTouch = createContext(false);
/** Marks the chrome over a phone's view, the strip and the rows under it, as touch-sized. */
export const StripTouchProvider = StripTouch.Provider;
/** Whether the strip in hand is a phone's: its tiles and chevrons are touch-sized. */
export const useStripTouch = () => useContext(StripTouch);
/** The class of a tile of the strip in hand. */
export const useStripButtonClass = () => useStripTouch() ? TOUCH_STRIP_BUTTON_CLASS : TOP_STRIP_BUTTON_CLASS;
