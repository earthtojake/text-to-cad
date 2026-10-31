import { useState } from "react";
import { Check } from "lucide-react";
import { RadioGroup } from "radix-ui";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { useI18n } from "@text-to-cad/ui/i18n";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import { useStripButtonClass } from "../tools/FloatingToolBar.js";

const ROW_CLASS = "relative flex min-h-7 w-full cursor-pointer items-center gap-2 rounded-sm py-1.5 pr-8 pl-2 text-left text-tiny leading-4 outline-none hover:bg-accent focus-visible:bg-accent focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45 disabled:pointer-events-none disabled:opacity-50";

function ModeChoice({ value, Icon, children, ...props }) {
  return <RadioGroup.Item value={value} className={ROW_CLASS} {...props}>
    <Icon className="size-3.5 shrink-0" aria-hidden="true" />{children}
    <span className="pointer-events-none absolute right-2 flex size-3.5 items-center justify-center" aria-hidden="true">
      <RadioGroup.Indicator><Check className="size-3.5" /></RadioGroup.Indicator>
    </span>
  </RadioGroup.Item>;
}

const PROJECTIONS = Object.freeze([
  { value: "orthographic", key: "projection.orthographic", label: "Orthographic", Icon: OrthographicProjectionIcon },
  { value: "perspective", key: "projection.perspective", label: "Perspective", Icon: PerspectiveProjectionIcon },
]);

/**
 * The camera's projection, a menu of its own beside Display's (every 3D view has one, while not
 * every view has display modes to choose): its tile is the projection on screen, its rows Orthographic and
 * Perspective, a choice closing it. Its own tile opens it; on a phone's strip with no room for that
 * tile it opens from the strip's More button instead (`anchor`, with `open` held by the strip).
 *
 * @param {{ projection: { value: string, onChange(value: string): void }, disabled?: boolean,
 *   boundary?: Element | null, tooltipSide?: "top" | "bottom", anchor?: import("react").RefObject<HTMLElement> | null,
 *   open?: boolean, onOpenChange?: (open: boolean) => void }} props
 */
export default function ProjectionPopover({ projection, disabled = false, boundary = null, tooltipSide = "top",
  anchor = null, open: held, onOpenChange }) {
  const { t } = useI18n();
  const [ownOpen, setOpen] = useState(false);
  const open = held ?? ownOpen;
  const stripClass = useStripButtonClass();
  const current = PROJECTIONS.find(option => option.value === projection.value) || PROJECTIONS[0];
  const changeOpen = next => { setOpen(next); onOpenChange?.(next); };
  return <Popover open={open} onOpenChange={changeOpen}>
    {anchor ? <PopoverAnchor virtualRef={anchor} /> : <PopoverTrigger asChild>
      <ToolbarButton label={t("projection.current", { mode: t(`projection.${current.value}`) })} tooltip={t("projection.label")} tooltipSide={tooltipSide} disabled={disabled}
        className={stripClass} data-projection={current.value}>
        <current.Icon />
      </ToolbarButton>
    </PopoverTrigger>}
    <PopoverContent align="center" sideOffset={6} collisionPadding={8} collisionBoundary={boundary || undefined} aria-label={t("projection.label")}
      className={cn(FLOATING_SURFACE_CLASS, "w-36 p-1 text-tiny data-[state=closed]:animate-none!")}>
      <div className="px-2 py-1.5 text-muted-foreground">{t("projection.label")}</div>
      <RadioGroup.Root aria-label={t("projection.label")} value={current.value} onValueChange={value => { projection.onChange(value); changeOpen(false); }}>
        {PROJECTIONS.map(({ value, Icon }) => <ModeChoice key={value} value={value} Icon={Icon}
          onClick={() => { if (value === current.value) changeOpen(false); }}>{t(`projection.${value}`)}</ModeChoice>)}
      </RadioGroup.Root>
    </PopoverContent>
  </Popover>;
}
