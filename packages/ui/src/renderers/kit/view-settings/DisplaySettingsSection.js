import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useMemo, useRef } from "react";
import { Blend, Expand, Plus, RotateCcw, RotateCw, Sun, SunDim, X } from "lucide-react";
import { ALL_VIEW_FEATURES, normalizeViewFeatures, normalizeViewSettings, resolveViewSettings, viewSettingsAreCustom } from "@text-to-cad/core/common/viewSettings.js";
import { MAX_THEME_FILL_COLORS } from "@text-to-cad/core/lib/themeSettings.js";
import { Button } from "@text-to-cad/ui/primitives/button";
import { useI18n } from "@text-to-cad/ui/i18n";
import { DISPLAY_MODE_OPTIONS } from "./DisplayModeOptions.js";
import {
  FileSheetColorPicker, FileSheetColorProperty,
  FileSheetControlRow, FileSheetSelectRow, FileSheetSettingsSection,
  FileSheetFieldGrid, FileSheetNumberProperty, parseFileSheetNumberInput
} from "../inspector/FileSheet.js";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";

// The panels' choices are values with icons; their labels are the locale's, read
// through `t` where they are shown (a locale change re-renders the section). Each
// table's words live in the dictionaries under the key family named here.
const PROJECTIONS = Object.freeze({
  orthographic: { labelKey: "display.projection.orthographic", icon: <OrthographicProjectionIcon className="size-3 shrink-0" /> },
  perspective: { labelKey: "display.projection.perspective", icon: <PerspectiveProjectionIcon className="size-3 shrink-0" /> }
});
const PART_COLOR_OPTIONS = [
  { value: "original", labelKey: "display.partColorMode.original" }, { value: "single", labelKey: "display.partColorMode.single" }, { value: "by-part", labelKey: "display.partColorMode.byPart" }
];
// Surface styles mirror the CLI; presets are shortcuts over these same controls.
const SURFACE_STYLE_OPTIONS = [
  { value: "shaded", labelKey: "display.style.shaded" }, { value: "flat", labelKey: "display.style.flat" },
  { value: "hidden", labelKey: "display.style.hidden" }, { value: "off", labelKey: "display.style.off" }
];
const FLOOR_PLACEMENT_OPTIONS = [{ value: "origin", labelKey: "display.floorPlacement.origin" }, { value: "lowest", labelKey: "display.floorPlacement.lowest" }];
// Glossy reflects the model too, at the cost of a second, smaller draw of the scene.
const FLOOR_FINISH_OPTIONS = [{ value: "matte", labelKey: "display.finish.matte" }, { value: "glossy", labelKey: "display.finish.glossy" }];

/** A select's choices with their labels in the locale, from a table of values and label keys. */
const labeled = (t, options) => options.map(({ labelKey, ...option }) => ({ ...option, label: t(labelKey) }));

function ColorPalette({ colors, onChange }) {
  const { t } = useI18n();
  const palette = Array.isArray(colors) && colors.length ? colors : ["#ffffff"];
  const commit = (next) => onChange(next.filter(Boolean).slice(0, MAX_THEME_FILL_COLORS));
  return (
    <FileSheetControlRow label={t("display.colors")} value={`${palette.length}/${MAX_THEME_FILL_COLORS}`}>
      <div className="flex flex-wrap gap-1.5">
        {palette.map((color, index) => (
          <div key={`${index}:${color}`} className="group relative">
            <FileSheetColorPicker
              value={color}
              swatchClassName="size-5"
              onChange={(nextColor) => commit(palette.map((entry, colorIndex) => (
                colorIndex === index ? nextColor : entry
              )))}
              aria-label={t("display.partColorN", { n: index + 1 })}
            />
            {palette.length > 1 ? (
              <Button
                type="button"
                variant="outline"
                size="icon-xs"
                className="absolute -right-1.5 -top-1.5 size-4 rounded-full bg-background p-0 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
                onClick={() => commit(palette.filter((_, colorIndex) => colorIndex !== index))}
                aria-label={t("display.removePartColor", { n: index + 1 })}
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
            aria-label={t("display.addPartColor")}
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

/**
 * Display's sections, stacked in its dropdown's one scroller (`DisplayPopover.jsx`). A
 * section with `onEnabledChange` is a feature gate (expanded IS enabled); the others are always
 * open. A press on an open gate's title scrolls it into view within the scroller's natural range,
 * never adding space to force it to the top, and never disables it.
 */
function DisplaySections({ sections }) {
  const list = useRef(null);
  const reveal = id => {
    const element = list.current?.closest('[data-slot="scroll-area-viewport"]') || list.current;
    const target = list.current?.querySelector(`[data-settings-section="${CSS.escape(id)}"] [data-settings-section-body]`);
    if (!target) return;
    const top = element.scrollTop + target.getBoundingClientRect().top - element.getBoundingClientRect().top
      - (target.previousElementSibling?.getBoundingClientRect().height || 0);
    element.scrollTop = Math.max(0, Math.min(top, element.scrollHeight - element.clientHeight));
  };
  return <div ref={list} data-settings-sections="">
    {sections.filter(Boolean).map(section => {
      const gated = typeof section.onEnabledChange === "function";
      return <FileSheetSettingsSection key={section.id} sectionId={section.id} title={section.title} headingAction={section.headingAction}
        open={gated ? section.enabled === true : true} onOpenChange={gated ? section.onEnabledChange : undefined}
        gated={gated} onReveal={() => reveal(section.id)}>{section.content}</FileSheetSettingsSection>;
    })}
  </div>;
}

export function DisplaySettingsSection({
  viewSettings = {}, resolvedView, hostAppearance = "light", lightingQuality = "final", onViewSettingsPatch, onGroupEnabledChange, onModeChange, onViewReset,
  features = ALL_VIEW_FEATURES, appearanceControl = null, close = null
}) {
  const { t } = useI18n();
  const settings = useMemo(() => normalizeViewSettings(viewSettings), [viewSettings]);
  const view = resolvedView || resolveViewSettings(settings, { appearance: hostAppearance, lightingQuality, features });
  // The panel is built from what its caller opted into: sections it mounts, presets and surface styles it lists.
  const offered = useMemo(() => normalizeViewFeatures(features), [features]);
  const offers = id => offered.sections.includes(id);
  // The render modes' names and what each says are the locale's, over the value (`mode.solid` and `mode.solid.title`).
  const modeOptions = DISPLAY_MODE_OPTIONS.filter(option => offered.modes.includes(option.value))
    .map(({ label, title, ...option }) => ({ ...option, label: t(`mode.${option.value}`), title: t(`mode.${option.value}.title`) }));
  const surfaceStyleOptions = labeled(t, SURFACE_STYLE_OPTIONS.filter(option => offered.surfaceStyles.includes(option.value)));
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
          <FileSheetSelectRow hideLabel className="px-0" label={t("display.surfaceStyle")} value={view.surfaces.style} onValueChange={style => setGroup("surfaces", { style })} options={surfaceStyleOptions} />
          <FileSheetSelectRow hideLabel className="px-0" label={t("display.parts")} value={view.surfaces.colorMode} onValueChange={colorMode => setGroup("surfaces", { colorMode })} options={labeled(t, PART_COLOR_OPTIONS)} />
        </FileSheetFieldGrid>
        {view.surfaces.colorMode === "single" ? color("surfaces", t("display.partColor")) : null}
        {view.surfaces.colorMode === "by-part" ? <ColorPalette colors={view.surfaces.colors} onChange={colors => setGroup("surfaces", { colors })} /> : null}
        {view.surfaces.colorMode !== "single" ? <FileSheetFieldGrid columns={1}><NumberProperty label={t("display.surfaceOpacity")} Icon={Blend} value={view.surfaces.opacity * 100} min={0} max={100} unit="%" digits={0} onChange={value => setGroup("surfaces", { opacity: value / 100 })} /></FileSheetFieldGrid> : null}
  </>;
  const sections = [
      offers("mode") && { id: "display", title: t("display.label"), headingAction: <TooltipHint content={t("display.resetDisplay")}><Button type="button" variant="ghost" size="icon-xs" aria-label={t("display.reset")}  className="size-5 text-muted-foreground" onClick={onViewReset}><RotateCcw className="size-3" aria-hidden="true" /></Button></TooltipHint>, content: <>
        <FileSheetFieldGrid columns={1}>
          <FileSheetSelectRow hideLabel className="px-0" label={t("display.mode")} value={custom ? "" : selectedMode.value} placeholder={t("display.custom")} onValueChange={onModeChange}
            triggerContent={custom ? undefined : <span className="flex min-w-0 items-center gap-1"><ModeIcon className="size-3 shrink-0" aria-hidden="true" /><span className="truncate">{presetLabel}</span></span>}
            triggerClassName="gap-1 px-1.5 [&_svg]:size-3"
            options={modeOptions.map(({ Icon, ...option }) => ({ ...option, icon: <Icon className="size-3.5" aria-hidden="true" /> }))} />
        </FileSheetFieldGrid>
        <FileSheetFieldGrid columns={appearanceControl ? 2 : 1}>
          {appearanceControl}
          <FileSheetSelectRow hideLabel className="px-0" label={t("display.projection")} value={view.camera.projection}
            onValueChange={projection => setGroup("camera", { projection })}
            // Its own trigger content, like Mode's: a narrow column ends the label in an ellipsis.
            triggerContent={<span className="flex min-w-0 items-center gap-1">{PROJECTIONS[view.camera.projection]?.icon}<span className="truncate">{t(PROJECTIONS[view.camera.projection]?.labelKey)}</span></span>}
            options={Object.entries(PROJECTIONS).map(([value, { labelKey, icon }]) => ({ value, label: t(labelKey), icon }))} />
        </FileSheetFieldGrid>
      </> },
      offers("surfaces") && { id: "surfaces", title: t("display.section.surfaces"), content: surfaces },
      section("edges", t("display.section.edges"), <FileSheetFieldGrid>
        <FileSheetSelectRow hideLabel className="px-0" label={t("display.edgeVisibility")} value={view.edges.visibility} onValueChange={visibility => setGroup("edges", { visibility })}
          options={[{ value: "visible", label: t("display.edgeVisibility.visible") }, { value: "all", label: t("display.edgeVisibility.all") }]} />
        <FileSheetColorProperty className="px-0" label={t("display.edgeColor")} value={view.edges.color} onChange={value => setGroup("edges", { color: value })} />
      </FileSheetFieldGrid>),
      (offers("grid") || offers("axes")) && { id: "grid-axes", title: t("display.section.gridAxes"),
        enabled: view.grid.enabled || view.axes.enabled,
        onEnabledChange: enabled => { if (offers("grid")) onGroupEnabledChange("grid", enabled); if (offers("axes")) onGroupEnabledChange("axes", enabled); },
        content: <FileSheetFieldGrid>{offers("grid") && color("grid", t("display.gridColor"), "px-0")}{offers("axes") && color("axes", t("display.axisColor"), "px-0")}</FileSheetFieldGrid> },
      section("lighting", t("display.section.lighting"), <>
        <FileSheetSelectRow hideLabel label={t("display.quality")} value={view.lighting.quality} onValueChange={quality => setGroup("lighting", { quality })}
          options={[{ value: "preview", label: t("display.quality.preview") }, { value: "final", label: t("display.quality.final") }]} />
        <FileSheetFieldGrid className="gap-1">
          <NumberProperty label={t("display.exposure")} Icon={Sun} value={view.lighting.exposure} min={-5} max={5} unit=" EV" digits={1} onChange={exposure => setGroup("lighting", { exposure })} />
          <NumberProperty label={t("display.rotation")} Icon={RotateCw} value={view.lighting.rotation} min={-180} max={180} unit="°" digits={0} onChange={rotation => setGroup("lighting", { rotation })} />
          <NumberProperty label={t("display.softboxSize")} Icon={Expand} value={view.lighting.size} min={0.25} max={3} unit="×" onChange={size => setGroup("lighting", { size })} />
          <NumberProperty label={t("display.fillRatio")} Icon={SunDim} value={view.lighting.fill * 100} min={0} max={100} unit="%" digits={0} onChange={value => setGroup("lighting", { fill: value / 100 })} />
        </FileSheetFieldGrid>
      </>),
      section("background", t("display.section.background"), color("background", t("display.backgroundColor"))),
      section("floor", t("display.section.floor"), <>
        {color("floor", t("display.floorColor"))}
        <FileSheetFieldGrid>
          <FileSheetSelectRow hideLabel className="px-0" label={t("display.floorPosition")} value={view.floor.placement} onValueChange={placement => setGroup("floor", { placement })}
            options={labeled(t, FLOOR_PLACEMENT_OPTIONS)} />
          <FileSheetSelectRow hideLabel className="px-0" label={t("display.floorFinish")} value={view.floor.finish} onValueChange={finish => setGroup("floor", { finish })}
            options={labeled(t, FLOOR_FINISH_OPTIONS)} />
        </FileSheetFieldGrid>
      </>),
  ];
  // Its dropdown has no heading: the first always-open section's heading row is its first row, and
  // carries the dropdown's X (`close`: `DisplayPopoverClose`) after its own action.
  const lead = sections.findIndex(item => item && typeof item.onEnabledChange !== "function");
  if (lead >= 0 && close) sections[lead] = { ...sections[lead], headingAction: <>{sections[lead].headingAction}{close}</> };
  return <div className="[&_[data-settings-section-heading]_.text-xs]:text-tiny">
    <DisplaySections sections={sections} />
  </div>;
}
