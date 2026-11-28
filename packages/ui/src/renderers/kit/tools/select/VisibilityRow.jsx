import { EyeOff, Focus } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import SubToolbar, { SubToolbarSeparator } from "../SubToolbar.jsx";
import { useI18n } from "@cad/ui/i18n";

const WORD_BUTTON_CLASS = "px-2 text-ui font-normal text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground dark:hover:bg-foreground/10";

/**
 * Select's row under the strip, there only while something is hidden or isolated: what the view leaves out, said where
 * the model is, with its way back, so a part hidden from the bar over it (`SelectionActionBar.jsx`) or from the panel
 * comes back without opening the panel. Hidden: an eye crossed out and the count ("2 hidden"), Undo while the last
 * hide can be undone (`onUndo`, else none), and Show all. Isolated: Exit isolate (Exit all isolates for several).
 * Nothing at all while nothing is left out: Select has no row of its own.
 *
 * @param {{ hiddenCount: number, onShowAll(): void, onUndo?: (() => void) | null,
 *   isolatedCount?: number, onExitIsolate?: (() => void) | null, disabled?: boolean }} props
 */
export default function VisibilityRow({ hiddenCount, onShowAll, onUndo = null, isolatedCount = 0, onExitIsolate = null, disabled = false }) {
  const { t } = useI18n();
  const hidden = hiddenCount > 0, isolated = isolatedCount > 0 && typeof onExitIsolate === "function";
  if (!hidden && !isolated) return null;
  return <SubToolbar label={t("tree.hiddenParts")} className="w-max flex-nowrap items-center" data-visibility-row="">
    {hidden ? <>
      <span className="flex items-center gap-1.5 px-1.5 text-ui text-muted-foreground" data-hidden-count="">
        <EyeOff className="size-3.5 shrink-0" aria-hidden="true" />
        {t("tree.hiddenCount", { count: hiddenCount.toLocaleString() })}
      </span>
      {onUndo ? <Button type="button" variant="ghost" size="sm" disabled={disabled} className={WORD_BUTTON_CLASS} data-action="undo-hide" onClick={onUndo}>
        {t("tree.undoHide")}
      </Button> : null}
      <Button type="button" variant="ghost" size="sm" disabled={disabled} className={WORD_BUTTON_CLASS} data-action="show-all" onClick={onShowAll}>
        {t("tree.showAll")}
      </Button>
    </> : null}
    {hidden && isolated ? <SubToolbarSeparator /> : null}
    {isolated ? <Button type="button" variant="ghost" size="sm" disabled={disabled} className={WORD_BUTTON_CLASS} data-action="exit-isolate" onClick={onExitIsolate}>
      <Focus className="size-3.5" aria-hidden="true" />
      {isolatedCount > 1 ? t("menu.exitAllIsolates") : t("tree.exitIsolate")}
    </Button> : null}
  </SubToolbar>;
}
