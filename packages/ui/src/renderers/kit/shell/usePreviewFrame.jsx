import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import LoadingStep from "../../../loading/LoadingStep.jsx";
import { Button } from "@cad/ui/primitives/button";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { useI18n } from "@cad/ui/i18n";
import { NAVBAR_CONTROL_CLASS } from "../../../lib/navbarRow.js";
import { useControlUsage } from "../../../usage/controls.js";
import { useStripButtonClass } from "../tools/FloatingToolBar.js";
import { backdropScheme, relativeLuminance, usePreviewIdle } from "../tools/PreviewChrome.jsx";
import { PreviewIcon } from "./PreviewIcon.jsx";
import { DisplayIcon } from "./DisplaySettings.jsx";
import { NAVBAR_VIEW_PLACE } from "./NavbarViewControls.jsx";
import PreviewSettings from "./PreviewSettings.jsx";
import { previewCoverStep } from "./previewCover.js";

// Preview's cover: at least this long, then until publication and the picture are ready.
// The picture is checked this often until it has converged.
// The cover waits at least MIN; at MAX it stops waiting for more components, and lets the picture on
// screen finish converging for at most FINISH more.
const PREVIEW_COVER_MIN_MS = 700, PREVIEW_COVER_QUIET_MS = 400, PREVIEW_COVER_MAX_MS = 5000, PREVIEW_COVER_FINISH_MS = 1000,
  PREVIEW_COVER_CONVERGE_MS = 50;

/** One of Preview's bar's controls: the navbar's icon button, named on hover, below it. */
function BarControl({ label, active = undefined, disabled = false, onClick, children, ...props }) {
  return <TooltipHint content={label} side="bottom" disabled={active === true}>
    <Button type="button" variant="ghost" size="icon-xs" aria-label={label} aria-pressed={active} disabled={disabled} onClick={onClick}
      className={NAVBAR_CONTROL_CLASS} {...props}>{children}</Button>
  </TooltipHint>;
}

function ViewControl({ label, disabled = false, tooltipSide = "top", onClick, children }) {
  return <ToolbarButton label={label} tooltipSide={tooltipSide} disabled={disabled} onClick={onClick} className={useStripButtonClass()}>
    {children}
  </ToolbarButton>;
}

/**
 * Preview's frame, for whichever frame offers Preview (`RendererShell.jsx`, a 3D view's; `FlatViewFrame.jsx`, a flat
 * view's whose picture can be shown in 3D): everything of Preview that is the same in every view, over the one
 * `previewing` state its caller holds (`useRendererShell.js`'s `usePreviewState`).
 *
 * - **Entering and leaving.** `enter()` covers the view first, in the frame of the press ("Preparing preview…"), and
 *   sets the state under the cover; `leave()` clears it. A new file (`modelKey`) leaves Preview.
 * - **The cover.** Up from the press until Preview's view has presented its first frame, its publication is
 *   complete (`view.complete`, false while what it draws is still arriving) and its picture has converged
 *   (`previewCover.js`) — unless the view is `moving` (Orbit, a routine playing), which has nothing to wait for — or
 *   at most a few seconds. Then it fades from the finished picture. Leaving needs none.
 * - **The host's navbar** steps aside while Preview is up (`fileView.onPreviewChange`).
 * - **Preview's bar and panel** (`PreviewChrome`'s props): the file's name, Display (a toggle, in Display's cube,
 *   `DisplayIcon`, at its size: how the picture is looked at, in Preview as outside it; the panel Orbit and its speed,
 *   then `render`, Render's own settings) and Exit preview, in the backdrop's ink, gone while the pointer rests
 *   (`usePreviewIdle` over `hostElement`).
 * - **Preview's view**, the frame's underlay: `View` (`PreviewView.jsx`, or a view's own around it) mounted while
 *   Preview is up, handed `view`, the scene to draw (`desired`), `viewRef` and the Orbit.
 * - **The Preview button**, a play triangle drawn to pair with Display's cube (`PreviewIcon.jsx`): the navbar's
 *   (`navbarButton`, after Display) and the strip's last entry where there is no navbar (`stripView`: its tile, and its
 *   row of a phone's More).
 *
 * @param {object} options
 * @param {boolean} options.previewing  The one presentation state.
 * @param {(previewing: boolean) => void} options.setPreviewing
 * @param {string} options.modelKey  The file on screen: another leaves Preview.
 * @param {object} options.fileView  The renderer's props: the file's name, `onPreviewChange`.
 * @param {HTMLElement | null} options.hostElement  The frame's root: where the pointer resting is watched.
 * @param {string} options.stageColor  The view's canvas colour: the cover's where Preview's Background is not set.
 * @param {"light" | "dark"} options.viewportScheme  The viewport's scheme, where Preview's Background says nothing.
 * @param {import("react").ComponentType<object>} options.View  Preview's view.
 * @param {object | null} options.view  What `View` draws (`RendererShell`'s `previewView`); null: nothing to mount yet.
 * @param {object} options.desired  The scene Preview draws (`previewViewScene.js`).
 * @param {string} options.sceneScaleMode
 * @param {{ current: object | null }} options.viewRef  Preview's viewport's handle.
 * @param {boolean} options.moving  The view moves on purpose (Orbit, a routine playing).
 * @param {boolean} options.orbit
 * @param {(orbit: boolean) => void} options.onOrbitChange
 * @param {number | null | undefined} options.orbitSpeed
 * @param {(speed: number) => void} options.onOrbitSpeedChange
 * @param {object} options.render  Render's own settings and their writes (`PreviewRenderSettings.jsx`'s `render`).
 * @param {boolean} options.disabled  No model yet: the button and the settings wait.
 * @param {boolean} options.mobile
 */
export function usePreviewFrame({ previewing, setPreviewing, modelKey, fileView, hostElement, stageColor, viewportScheme, View, view, desired,
  sceneScaleMode, viewRef, moving, orbit, onOrbitChange, orbitSpeed, onOrbitSpeedChange, render, disabled, mobile }) {
  const { t } = useI18n();
  const controls = useControlUsage();
  // Preview's settings panel: closed as Preview opens, until its button brings it out.
  const [panelOpen, setPanelOpen] = useState(false);
  // Preview is a view of its own, mounted over the editor's as it opens (`PreviewView.jsx`), and
  // its first picture takes a moment on a large model — its scene built from the published mesh
  // and remaining components arriving — so it is covered ("Preparing preview…") until
  // its first frame is presented (`presented`), the publication is complete,
  // and its picture converged (every sample of its frame drawn: the view's `pictureProgress`) — unless
  // it starts over, the view moving (a routine playing), when there is nothing to wait for — or at most
  // a few seconds. Then the cover fades away from the finished picture. Leaving needs no cover: the
  // Preview's view goes, and under it is the editor's, as it was.
  const [presented, setPresented] = useState(false);
  const presentedRef = useRef(false);
  presentedRef.current = previewing && presented;
  // A press covers the view first, in its own frame, and preview is entered under it: preview's
  // first render can take a moment on a large model, and the cover answers the press at once.
  const [coverRequested, setCoverRequested] = useState(false);
  // The cover is preview's from the render that enters it, so not one frame of preview shows
  // before it: settled is reset there, and set once preview has come together. Each crossing is
  // taken in the render that makes it, never in an effect after it (another commit): entering also
  // answers the press's request and closes the settings panel.
  const [settled, setSettled] = useState(false);
  const [coverFor, setCoverFor] = useState(previewing);
  if (coverFor !== previewing) {
    setCoverFor(previewing);
    setSettled(false);
    setPresented(false);
    if (previewing) { setCoverRequested(false); setPanelOpen(false); }
  }
  const covered = coverRequested || (previewing && !settled);
  // What moves Preview's picture on purpose: its Orbit, or its routine playing (`previewCover.js`).
  const movingRef = useRef(false);
  movingRef.current = moving;
  const loadingRef = useRef(false);
  loadingRef.current = view?.complete === false;
  useEffect(() => {
    if (!previewing) return undefined;
    let quiet = 0, done = false, capped = false;
    const finish = () => { if (done) return; done = true; setSettled(true); };
    // Published components still streaming (a model opened cold) is waited for this long, no longer; then the
    // picture on screen converges, and the cover lifts on it, or at the last at FINISH more.
    const cap = setTimeout(() => { capped = true; settle(0); }, PREVIEW_COVER_MAX_MS);
    const last = setTimeout(finish, PREVIEW_COVER_MAX_MS + PREVIEW_COVER_FINISH_MS);
    const settle = (delay = PREVIEW_COVER_QUIET_MS) => {
      clearTimeout(quiet);
      quiet = setTimeout(() => {
        const step = previewCoverStep({ presented: presentedRef.current, loading: loadingRef.current && !capped, moving: movingRef.current,
          progress: viewRef.current?.pictureProgress?.() ?? null });
        if (step === "wait") settle();
        else if (step === "converge") settle(PREVIEW_COVER_CONVERGE_MS);
        else finish();
      }, delay);
    };
    settle(PREVIEW_COVER_MIN_MS);
    return () => { done = true; clearTimeout(cap); clearTimeout(last); clearTimeout(quiet); };
  }, [previewing]);
  useEffect(() => { setPreviewing(false); }, [modelKey, setPreviewing]);
  // Preview is a view of its own (`PreviewView.jsx`): it opens on the model as authored, in Render,
  // still, its routine at rest until the person plays it, and leaving it takes it away.
  const enter = () => {
    setCoverRequested(true);
    // After the frame the cover is painted in (a hidden page paints none: a timer stands in).
    let entered = false;
    const go = () => { if (!entered) { entered = true; setPreviewing(true); } };
    requestAnimationFrame(() => setTimeout(go, 0));
    setTimeout(go, 100);
  };
  const leave = () => setPreviewing(false);
  // Preview's bar names what it shows: the file's name, or its path's last part.
  const name = fileView.file?.name || String(fileView.file?.path ?? "").split("/").pop() || "";
  // While Preview is up the host's chrome steps aside (FileViewer's navbar): said as it opens, and as
  // it closes or the view goes.
  // Preview's bar and its playbar, shown and gone together while the pointer rests; its settings open hold them.
  const idle = usePreviewIdle(hostElement, previewing, panelOpen);
  const onPreviewChange = fileView.onPreviewChange;
  useEffect(() => {
    if (!previewing || !onPreviewChange) return undefined;
    onPreviewChange(true);
    return () => onPreviewChange(false);
  }, [previewing, onPreviewChange]);
  // Preview: the tools put away and the host's navbar too (FileViewer hides it while
  // `fileView.onPreviewChange` says Preview is up), the model in Render — the tools view never is — and
  // still until Orbit is turned on. In the navbar's place, Preview's own bar over the view's top edge,
  // on no surface, gone while the pointer rests (`PreviewChrome`): the file's name, and at its right its
  // settings (a toggle, the panel docked under it at the view's right edge: Orbit, Render's own), closed
  // as it opens, and the way out. The same in every host.
  // Its chrome over the model in the backdrop's ink (Preview's Background, else the viewport's canvas), never the app's.
  const scheme = backdropScheme(desired?.view?.background, viewportScheme);
  const preview = { active: previewing, name, idle, panelOpen, scheme,
    controls: <>
      <BarControl label={t("preview.settings")} active={panelOpen} disabled={disabled}
        onClick={() => { if (!panelOpen) controls.used("preview_settings"); setPanelOpen(open => !open); }} data-preview-settings=""><DisplayIcon className="size-4" aria-hidden="true" /></BarControl>
      <BarControl label={t("preview.exit")} onClick={leave}><X className="size-3.5" aria-hidden="true" /></BarControl>
    </>,
    panel: <PreviewSettings orbit={orbit} onOrbitChange={onOrbitChange}
      speed={orbitSpeed || 1} onSpeedChange={onOrbitSpeedChange}
      onClose={() => setPanelOpen(false)} render={render} /> };
  // Preview: a view of its own over the editor's, mounted while it is open.
  const underlay = previewing && view ? <div className="pointer-events-auto absolute inset-0 z-[1]" data-preview-view="">
    <View view={view} desired={desired} modelKey={modelKey}
      sceneScaleMode={sceneScaleMode} viewRef={viewRef} onPresented={setPresented}
      orbit={orbit} orbitSpeed={orbitSpeed ?? 1} />
  </div> : null;
  // Preview coming together underneath, covered on what Preview is about to show: its own backdrop (its Background, where
  // it is set and opaque enough to read on), else the view's canvas, as it was; in that backdrop's ink (`scheme`: the
  // Background's, else the viewport's), never the app's.
  const backdrop = desired?.view?.background;
  const coverColor = backdrop?.enabled !== false && Number(backdrop?.opacity ?? 1) >= 0.5 && relativeLuminance(backdrop?.color) !== null
    ? backdrop.color : stageColor;
  const overlays = <div aria-hidden={!covered} data-preview-cover={covered ? "" : undefined} data-scheme={scheme}
    className={cn("absolute inset-0 z-40 flex items-center justify-center", scheme,
      // At once over the press, so nothing of preview shows first; it fades only as it lifts.
      covered ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0 transition-opacity duration-300 motion-reduce:transition-none")}
    style={{ backgroundColor: coverColor }}>
    {/* The one indicator (`loading/LoadingStep.jsx`) on Preview's own backdrop. */}
    {covered ? <LoadingStep label={t("preview.preparing")} className="mx-4" /> : null}
  </div>;
  // The button, a play triangle: the navbar's, after Display, or the strip's last entry (its tile, and its row of a phone's More).
  const navbarButton = <ToolbarButton label={t("preview.label")} tooltipSide="bottom" tooltip={!mobile} disabled={disabled} onClick={enter} className={NAVBAR_VIEW_PLACE.className} data-view-preview="">
    <PreviewIcon />
  </ToolbarButton>;
  const stripView = { id: "preview", label: t("preview.label"), icon: <PreviewIcon />, disabled, onSelect: enter,
    tile: <ViewControl label={t("preview.label")} disabled={disabled} onClick={enter}><PreviewIcon /></ViewControl> };
  return {
    previewing, enter, leave, idle, scheme,
    // `ViewFrame.jsx`'s props.
    frame: { previewing, preview, underlay, overlays },
    navbarButton, stripView
  };
}
