import { useState } from "react";
import { Radio, Square } from "lucide-react";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { useI18n } from "@cad/ui/i18n";
import { TOOL_PANEL_BUTTON_CLASS } from "../kit/tools/ToolPanel.jsx";
import { FileSheetStatusText } from "../kit/inspector/FileSheet.js";

// The same box as the Pose row's dropdown (`kinematicsControls.jsx`), as a text field.
const FIELD_CLASS = "h-6 min-w-0 flex-1 rounded-md border border-input bg-transparent px-[7px] text-tiny shadow-xs outline-none "
  + "placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/45 read-only:opacity-70 dark:bg-input/30";

function number(value, digits = 0) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : null;
}

/**
 * Position's Machine: the address of a machine's controller and Watch, which makes the twin follow
 * it (`useMachineMirror.js`); while it watches, Stop, and under it a line on what the machine is doing
 * and each thing the twin could not show. Laid out as the Pose row is: the field on the panel's 8px
 * line, the icon button in Reset's column.
 * @param {{ mirror: ReturnType<typeof import("./useMachineMirror.js").useMachineMirror> }} props
 */
export default function XbfMachineRow({ mirror }) {
  const { t } = useI18n();
  const [text, setText] = useState(mirror.address || "");
  const on = mirror.phase !== "idle";
  const axes = Object.keys(mirror.mapping.joints);
  const submit = () => {
    if (on) { mirror.stop(); return; }
    if (!text.trim()) return;
    mirror.watch(text);
  };
  const reading = mirror.state?.reading || null;
  const lines = [];
  if (!axes.length) lines.push(t("machine.noAxes"));
  for (const { reason } of mirror.mapping.refused) lines.push(reason);
  if (mirror.error) lines.push(mirror.error);
  else if (mirror.state?.error) lines.push(t("machine.lost", { error: mirror.state.error }));
  else if (mirror.phase === "connecting") lines.push(t("machine.connecting"));
  if (reading && mirror.phase === "watching") {
    const parts = [t(`machine.state.${reading.state}`)];
    if (reading.line != null) parts.push(t("machine.line", { line: reading.line }));
    if (number(reading.feed) != null) parts.push(t("machine.feed", { feed: number(reading.feed) }));
    if (number(reading.spindle) != null && Number(reading.spindle) > 0) parts.push(t("machine.spindle", { rpm: number(reading.spindle) }));
    lines.push(parts.join(" · "));
    for (const sentence of reading.assumed || []) lines.push(sentence);
  }
  const pose = mirror.pose;
  if (pose?.unmatched.length) lines.push(t("machine.unmatched", { axes: pose.unmatched.join(" ") }));
  if (pose?.idle.length) lines.push(t("machine.unreported", { axes: pose.idle.join(" ") }));
  if (pose?.past.length) lines.push(t("machine.past", { axes: pose.past.join(" ") }));
  const label = on ? t("machine.stop") : t("machine.watch");
  return <div className="space-y-1" data-machine-row="">
    <form className="flex h-8 items-center gap-1.5" onSubmit={event => { event.preventDefault(); submit(); }}>
      <input type="text" value={on ? mirror.address : text} readOnly={on} spellCheck={false} autoComplete="off"
        aria-label={t("machine.address")} placeholder={t("machine.placeholder")} className={FIELD_CLASS}
        onChange={event => setText(event.target.value)} data-machine-address="" />
      <TooltipHint content={label} side="bottom">
        <button type="submit" aria-label={label} data-machine-watch="" disabled={!on && (!axes.length || !text.trim())}
          className={cn(TOOL_PANEL_BUTTON_CLASS, "mr-1 disabled:pointer-events-none disabled:opacity-40", on && "text-foreground")}>
          {on ? <Square className="size-3" aria-hidden="true" /> : <Radio className="size-3" aria-hidden="true" />}
        </button>
      </TooltipHint>
    </form>
    {lines.map((line, index) => <FileSheetStatusText key={`${index}:${line}`} className="px-0">{line}</FileSheetStatusText>)}
  </div>;
}
