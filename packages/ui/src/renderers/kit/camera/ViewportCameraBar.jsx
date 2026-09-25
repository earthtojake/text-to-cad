import { useEffect, useState } from "react";
import { House, SlidersHorizontal } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@hardcore/ui/primitives/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@hardcore/ui/primitives/tooltip";
import { DISPLAY_MODE_OPTIONS } from "../view-settings/DisplayModeOptions.js";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "./ProjectionModeIcons.js";

const CONTROL = "flex h-6 items-center justify-center rounded px-1 text-muted-foreground enabled:hover:bg-accent enabled:hover:text-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";

/** Small, transparent camera controls, shared by every 3D viewport. */
export function ViewportCameraBar({ projection, onProjectionChange, mode, preset, modes, onModeChange, onReset, disabled = false }) {
  const [openMenu, setOpenMenu] = useState(null);
  useEffect(() => { if (disabled) setOpenMenu(null); }, [disabled]);
  const perspective = projection === "perspective";
  const ProjectionIcon = perspective ? PerspectiveProjectionIcon : OrthographicProjectionIcon;
  const projectionLabel = perspective ? "Perspective" : "Orthographic";
  const options = DISPLAY_MODE_OPTIONS.filter(option => !modes || modes.includes(option.value));
  const current = options.find(option => option.value === mode);
  const base = options.find(option => option.value === preset);
  const ModeIcon = current?.Icon || base?.Icon || SlidersHorizontal;
  return <TooltipProvider delayDuration={300}><div className="flex items-center justify-center gap-0.5" aria-label="View controls">
    {onReset ? <Tooltip open={disabled ? false : undefined}><TooltipTrigger asChild><button type="button" disabled={disabled} className={CONTROL} aria-label="Reset to default isometric view"
      onClick={onReset}><House className="size-3.5" strokeWidth={1.45} aria-hidden="true" /></button></TooltipTrigger><TooltipContent side="top" sideOffset={4}>Reset</TooltipContent></Tooltip> : null}
    {onModeChange ? <DropdownMenu open={!disabled && openMenu === "mode"} onOpenChange={open => setOpenMenu(open ? "mode" : null)}>
      <Tooltip open={disabled ? false : undefined}><TooltipTrigger asChild><DropdownMenuTrigger asChild disabled={disabled}><button type="button" disabled={disabled} className={CONTROL} aria-label={`Display mode: ${current?.label || "Custom"}`}><ModeIcon className="size-3.5" aria-hidden="true" /></button></DropdownMenuTrigger></TooltipTrigger><TooltipContent side="top" sideOffset={4}>Mode</TooltipContent></Tooltip>
      <DropdownMenuContent side="top" align="end"><DropdownMenuRadioGroup value={mode} onValueChange={onModeChange}>
        {options.map(({ value, label, Icon }) => <DropdownMenuRadioItem key={value} value={value}><Icon className="size-3.5" aria-hidden="true" />{label}</DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup></DropdownMenuContent>
    </DropdownMenu> : null}
    {onProjectionChange ? <DropdownMenu open={!disabled && openMenu === "projection"} onOpenChange={open => setOpenMenu(open ? "projection" : null)}>
      <Tooltip open={disabled ? false : undefined}><TooltipTrigger asChild><DropdownMenuTrigger asChild disabled={disabled}>
        <button type="button" disabled={disabled} className={CONTROL} aria-label={`Projection: ${projectionLabel}`}>
          <ProjectionIcon className="size-3.5" />
        </button>
      </DropdownMenuTrigger></TooltipTrigger><TooltipContent side="top" sideOffset={4}>Projection</TooltipContent></Tooltip>
      <DropdownMenuContent side="top" align="end">
        <DropdownMenuRadioGroup value={projection} onValueChange={onProjectionChange}>
          <DropdownMenuRadioItem value="orthographic"><OrthographicProjectionIcon className="size-3.5" />Orthographic</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="perspective"><PerspectiveProjectionIcon className="size-3.5" />Perspective</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu> : null}
  </div></TooltipProvider>;
}
