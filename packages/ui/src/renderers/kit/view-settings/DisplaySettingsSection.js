import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { useMemo } from "react";
import { Blend, Expand, Plus, RotateCcw, RotateCw, Sun, SunDim, X } from "lucide-react";
import { ALL_VIEW_FEATURES, normalizeViewFeatures, normalizeViewSettings, resolveViewSettings, viewSettingsAreCustom } from "@hardcore/core/common/viewSettings.js";
import { MAX_THEME_FILL_COLORS } from "@hardcore/core/lib/themeSettings.js";
import { Button } from "@hardcore/ui/primitives/button";
import { DISPLAY_MODE_OPTIONS } from "./DisplayModeOptions.js";
import {
  FileSheetColorPicker, FileSheetColorProperty,
  FileSheetControlRow, FileSheetSelectRow,
  FileSheetFieldGrid, FileSheetNumberProperty, parseFileSheetNumberInput
} from "../inspector/FileSheet.js";

import FilePanelSections from "../inspector/FilePanelSections.jsx";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";

const PART_COLOR_OPTIONS = [
  { value: "original", label: "Original" }, { value: "single", label: "Single color" }, { value: "by-part", label: "Color by part" }
];
// Surface styles mirror the CLI; presets are shortcuts over these same controls.
const SURFACE_STYLE_OPTIONS = [
  { value: "shaded", label: "Shaded" }, { value: "flat", label: "Flat" },
  { value: "hidden", label: "Hidden" }, { value: "off", label: "Off" }
];

function ColorPalette({ colors, onChange }) {
  const palette = Array.isArray(colors) && colors.length ? colors : ["#ffffff"];
  const commit = (next) => onChange(next.filter(Boolean).slice(0, MAX_THEME_FILL_COLORS));
  return (
    <FileSheetControlRow label="Colors" value={`${palette.length}/${MAX_THEME_FILL_COLORS}`}>
      <div className="flex flex-wrap gap-1.5">
        {palette.map((color, index) => (
          <div key={`${index}:${color}`} className="group relative">
            <FileSheetColorPicker
              value={color}
              swatchClassName="size-5"
              onChange={(nextColor) => commit(palette.map((entry, colorIndex) => (
                colorIndex === index ? nextColor : entry
              )))}
              aria-label={`Part color ${index + 1}`}
            />
            {palette.length > 1 ? (
              <Button
                type="button"
                variant="outline"
                size="icon-xs"
                className="absolute -right-1.5 -top-1.5 size-4 rounded-full bg-background p-0 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
                onClick={() => commit(palette.filter((_, colorIndex) => colorIndex !== index))}
                aria-label={`Remove part color ${index + 1}`}
              >
                <X className="size-2.5" aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        ))}
        {palette.length < MAX_THEME_FILL_COLORS ? (
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className="size-7"
            onClick={() => commit([...palette, palette[palette.length - 1] || "#ffffff"])}
            aria-label="Add part color"
          >
            <Plus className="size-3.5" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </FileSheetControlRow>
  );
}

function NumberProperty({ label, Icon, value, min, max, unit = "", digits = 2, onChange }) {
  return <FileSheetNumberProperty label={label} Icon={Icon} value={`${Number(value).toFixed(digits)}${unit}`}
    onValueCommit={draft => onChange(parseFileSheetNumberInput(draft, { fallback: value, min, max }))} />;
}

export function DisplaySettingsSection({
  viewSettings = {}, resolvedView, hostAppearance = "light", lightingQuality = "final", onViewSettingsPatch, onGroupEnabledChange, onModeChange, onViewReset,
  edgeStatus = "idle", edgeError = "", features = ALL_VIEW_FEATURES, leadingSections = [], appearanceControl = null, sticky = true
}) {
  const settings = useMemo(() => normalizeViewSettings(viewSettings), [viewSettings]);
  const view = resolvedView || resolveViewSettings(settings, { appearance: hostAppearance, lightingQuality, features });
  // The panel is built from what its caller opted into: sections it mounts, presets and surface styles it lists.
  const offered = useMemo(() => normalizeViewFeatures(features), [features]);
  const offers = id => offered.sections.includes(id);
  const modeOptions = DISPLAY_MODE_OPTIONS.filter(option => offered.modes.includes(option.value));
  const surfaceStyleOptions = SURFACE_STYLE_OPTIONS.filter(option => offered.surfaceStyles.includes(option.value));
  // Sparse writes stay in the canonical settings store; the renderer never owns UI state.
  const setGroup = (group, patch) => onViewSettingsPatch({ [group]: {
    ...(group === "surfaces" || view[group]?.enabled === false ? { enabled: true } : {}), ...patch
  } });
  const custom = viewSettingsAreCustom(settings, { appearance: hostAppearance, lightingQuality, features });
  const selectedMode = modeOptions.find(option => option.value === view.mode) || modeOptions[0];
  const ModeIcon = selectedMode.Icon;
  const presetLabel = selectedMode.label;
  const section = (group, title, content) => !offers(group) ? null : ({
    id: group, title, content, enabled: view[group].enabled,
    onEnabledChange: enabled => onGroupEnabledChange(group, enabled),
  });
  const color = (group, label, className) => <FileSheetColorProperty className={className} label={label} value={view[group].color}
    onChange={value => setGroup(group, { color: value })} opacity={view[group].opacity}
    onOpacityChange={opacity => setGroup(group, { opacity })} />;
  const surfaces = <>
        <FileSheetFieldGrid>
          <FileSheetSelectRow hideLabel className="px-0" label="Surface style" value={view.surfaces.style} onValueChange={style => setGroup("surfaces", { style })} options={surfaceStyleOptions} />
          <FileSheetSelectRow hideLabel className="px-0" label="Parts" value={view.surfaces.colorMode} onValueChange={colorMode => setGroup("surfaces", { colorMode })} options={PART_COLOR_OPTIONS} />
        </FileSheetFieldGrid>
        {view.surfaces.colorMode === "single" ? color("surfaces", "Part color") : null}
        {view.surfaces.colorMode === "by-part" ? <ColorPalette colors={view.surfaces.colors} onChange={colors => setGroup("surfaces", { colors })} /> : null}
        {view.surfaces.colorMode !== "single" ? <FileSheetFieldGrid columns={1}><NumberProperty label="Surface opacity" Icon={Blend} value={view.surfaces.opacity * 100} min={0} max={100} unit="%" digits={0} onChange={value => setGroup("surfaces", { opacity: value / 100 })} /></FileSheetFieldGrid> : null}
  </>;
  const sections = [
      offers("mode") && { id: "display", title: "Display", collapsible: false, headingAction: <TooltipHint content="Reset display"><Button type="button" variant="ghost" size="icon-xs" aria-label="Reset"  className="size-5 text-muted-foreground" onClick={onViewReset}><RotateCcw className="size-3" aria-hidden="true" /></Button></TooltipHint>, content: <>
        <FileSheetFieldGrid columns={1}>
          <FileSheetSelectRow hideLabel className="px-0" label="Mode" value={custom ? "" : selectedMode.value} placeholder="Custom" onValueChange={onModeChange}
            triggerContent={custom ? undefined : <span className="flex min-w-0 items-center gap-1"><ModeIcon className="size-3 shrink-0" aria-hidden="true" /><span className="truncate">{presetLabel}</span></span>}
            triggerClassName="gap-1 px-1.5 [&_svg]:size-3"
            options={modeOptions.map(({ Icon, ...option }) => ({ ...option, icon: <Icon className="size-3.5" aria-hidden="true" /> }))} />
        </FileSheetFieldGrid>
        <FileSheetFieldGrid columns={appearanceControl ? 2 : 1}>
          {appearanceControl}
          <FileSheetSelectRow hideLabel className="px-0" label="Projection" value={view.camera.projection}
            onValueChange={projection => setGroup("camera", { projection })}
            options={[{ value: "orthographic", label: "Orthographic", icon: <OrthographicProjectionIcon className="size-3" /> },
              { value: "perspective", label: "Perspective", icon: <PerspectiveProjectionIcon className="size-3" /> }]} />
        </FileSheetFieldGrid>
      </> },
      offers("surfaces") && { id: "surfaces", title: "Surfaces", collapsible: false, content: surfaces },
      ...leadingSections,
      section("edges", "Edges", <FileSheetFieldGrid>
        <FileSheetSelectRow hideLabel className="px-0" label="Edge visibility" value={view.edges.visibility} onValueChange={visibility => setGroup("edges", { visibility })}
          options={[{ value: "visible", label: "Visible" }, { value: "all", label: "All" }]} />
        <FileSheetColorProperty className="px-0" label="Edge color" value={view.edges.color} onChange={value => setGroup("edges", { color: value })} />
      </FileSheetFieldGrid>),
      (offers("grid") || offers("axes")) && { id: "grid-axes", title: "Grid / Axes",
        enabled: view.grid.enabled || view.axes.enabled,
        onEnabledChange: enabled => { if (offers("grid")) onGroupEnabledChange("grid", enabled); if (offers("axes")) onGroupEnabledChange("axes", enabled); },
        content: <FileSheetFieldGrid>{offers("grid") && color("grid", "Grid color", "px-0")}{offers("axes") && color("axes", "Axis color", "px-0")}</FileSheetFieldGrid> },
      section("lighting", "Lighting", <>
        <FileSheetSelectRow hideLabel label="Quality" value={view.lighting.quality} onValueChange={quality => setGroup("lighting", { quality })}
          options={[{ value: "preview", label: "Preview" }, { value: "final", label: "Final" }]} />
        <FileSheetFieldGrid className="gap-1">
          <NumberProperty label="Exposure" Icon={Sun} value={view.lighting.exposure} min={-5} max={5} unit=" EV" digits={1} onChange={exposure => setGroup("lighting", { exposure })} />
          <NumberProperty label="Rotation" Icon={RotateCw} value={view.lighting.rotation} min={-180} max={180} unit="°" digits={0} onChange={rotation => setGroup("lighting", { rotation })} />
          <NumberProperty label="Softbox size" Icon={Expand} value={view.lighting.size} min={0.25} max={3} unit="×" onChange={size => setGroup("lighting", { size })} />
          <NumberProperty label="Fill ratio" Icon={SunDim} value={view.lighting.fill * 100} min={0} max={100} unit="%" digits={0} onChange={value => setGroup("lighting", { fill: value / 100 })} />
        </FileSheetFieldGrid>
      </>),
      section("background", "Background", color("background", "Background color")),
      section("floor", "Floor", <>
        {color("floor", "Floor color")}
        <FileSheetSelectRow hideLabel label="Floor position" value={view.floor.placement} onValueChange={placement => setGroup("floor", { placement })}
          options={[{ value: "origin", label: "Model origin" }, { value: "lowest", label: "Lowest point" }]} />
      </>),
  ];
  return <div className="flex min-h-0 flex-1 flex-col [&_[data-file-panel-heading]_.text-xs]:text-tiny" data-cad-display-settings-section="true">
    <FilePanelSections sections={sections} sticky={sticky} footer={edgeStatus === "loading" || edgeError ? <div className="space-y-1 border-t border-border py-1">
      {offers("edges") && edgeStatus === "loading" ? <p role="status" className="px-2 text-tiny text-muted-foreground">Preparing edges…</p> : null}
      {offers("edges") && edgeError ? <p role="alert" className="px-2 text-tiny text-destructive">Couldn’t load edges. {edgeError}</p> : null}
    </div> : null} />
  </div>;
}
