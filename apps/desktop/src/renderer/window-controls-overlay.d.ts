/**
 * The Window Controls Overlay API, which `lib/titlebar.ts` measures the macOS
 * traffic lights with. Chromium ships it and Electron turns it on per window
 * (`titleBarOverlay`), but TypeScript's DOM library has no declaration for it
 * — hence this one, which is exactly the part this app uses.
 */
interface WindowControlsOverlayGeometryChangeEvent extends Event {
  readonly titlebarAreaRect: DOMRect;
  readonly visible: boolean;
}

interface WindowControlsOverlay extends EventTarget {
  /** False when the platform has taken the controls away — fullscreen. */
  readonly visible: boolean;
  /** The area left over for the app: its `x` is the room the controls need. */
  getTitlebarAreaRect(): DOMRect;
  addEventListener(
    type: "geometrychange",
    listener: (event: WindowControlsOverlayGeometryChangeEvent) => void,
  ): void;
  removeEventListener(
    type: "geometrychange",
    listener: (event: WindowControlsOverlayGeometryChangeEvent) => void,
  ): void;
}

interface Navigator {
  /** Undefined unless the window was created with `titleBarOverlay`. */
  readonly windowControlsOverlay?: WindowControlsOverlay;
}
