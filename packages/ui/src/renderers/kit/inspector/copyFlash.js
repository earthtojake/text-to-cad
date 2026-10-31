import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { ViewerHostContext } from "../../../host/context.js";

const COPIED_MS = 1200;

/**
 * A copy by a click, through the host's clipboard (shared UI never discovers one): `copy(text)`
 * writes text and `copyImage(png)` a picture (a PNG, or the promise of one), and either says
 * "Copied" (`copied`) for a moment once it is there. Without a host there is nothing to copy to,
 * and `canCopy` is false.
 */
export function useCopyFlash() {
  const host = useContext(ViewerHostContext);
  const [copied, setCopied] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  const clipboard = host?.clipboard || null;
  const flash = useCallback(async write => {
    try { await write(); } catch { return false; }
    clearTimeout(timer.current);
    setCopied(true);
    timer.current = setTimeout(() => setCopied(false), COPIED_MS);
    return true;
  }, []);
  // `text` may be a promise of it: a chip that writes its file first, then copies the file's path.
  const copy = useCallback(text => (clipboard ? flash(async () => {
    const value = String((await text) || "").trim();
    if (!value) throw new Error("nothing to copy");
    await clipboard.writeText(value);
  }) : Promise.resolve(false)), [clipboard, flash]);
  const copyImage = useCallback(png => (clipboard ? flash(() => clipboard.writeImage(png)) : Promise.resolve(false)), [clipboard, flash]);
  return { canCopy: Boolean(clipboard), copied, copy, copyImage };
}
