import { createContext, useContext } from "react";

// The strip's tiles: 24px, their icons 14px (a little over half the tile), whatever size the icon
// was handed at. The view's controls after its tools (Display, Preview) are its tiles too. On a
// touch strip (a phone) they are 36px, their icons 18px.
export const STRIP_BUTTON_CLASS = "size-6 [&>svg]:size-3.5!";
export const TOUCH_STRIP_BUTTON_CLASS = "size-9 rounded-md [&>svg]:size-4.5!";

const StripTouch = createContext(false);
/** Marks the chrome over a phone's view, the strip and the rows under it, as touch-sized. */
export const StripTouchProvider = StripTouch.Provider;
/** Whether the strip in hand is a phone's: its tiles and chevrons are touch-sized. */
export const useStripTouch = () => useContext(StripTouch);
/** The class of a tile of the strip in hand. */
export const useStripButtonClass = () => useStripTouch() ? TOUCH_STRIP_BUTTON_CLASS : STRIP_BUTTON_CLASS;
