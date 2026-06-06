import { Children, isValidElement, useEffect, useId, useMemo, useRef, useState } from "react";
import { Contrast, FlipHorizontal2, Moon, MoreHorizontal, Pencil, Plus, RotateCcw, Sun, Trash2, X } from "lucide-react";
import {
  Accordion
} from "../ui/accordion";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from "../ui/alert-dialog";
import { Button } from "../ui/button";
import { ColorPicker } from "../ui/color-picker";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "../ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger
} from "../ui/dropdown-menu";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../ui/select";
import { Slider } from "../ui/slider";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger
} from "../ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { cn } from "@/ui/utils";
import {
  cloneThemePresetSettings,
  DEFAULT_THEME_PRESET_ID,
  THEME_PRESETS,
  THEME_COLOR_MODES,
  THEME_FLOOR_MODES,
  MAX_THEME_FILL_COLORS,
  normalizeThemePresetId,
  normalizeThemeSettings,
  resolveSystemThemePresetId
} from "cadjs/lib/themeSettings";
import {
  CAD_DISPLAY_MODE,
  normalizeDisplaySettings
} from "cadjs/lib/displaySettings";
import {
  buildStepClipPatch,
  clipAxisBounds,
  clipAxisPosition,
  DEFAULT_STEP_CLIP_SETTINGS,
  normalizeStepClipSettings
} from "cadjs/lib/viewer/clipPlane";
import FileSheet, {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_COMPACT_INPUT_CLASSES,
  FILE_SHEET_FIELD_LABEL_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FILE_SHEET_ROW_STACK_CLASSES,
  FILE_SHEET_SEGMENTED_ITEM_CLASSES,
  FileSheetControlRow,
  FileSheetSection,
  FileSheetSliderField,
  FileSheetSubsection,
  FileSheetSubsubsection,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet";

const BACKGROUND_MODE_OPTIONS = [
  { value: "solid", label: "Solid" },
  { value: "linear", label: "Linear" },
  { value: "radial", label: "Radial" },
  { value: "transparent", label: "Transparent" }
];

const DISPLAY_MODE_OPTIONS = [
  { value: CAD_DISPLAY_MODE.SOLID, label: "Solid", title: "Shaded with CAD edges" },
  { value: CAD_DISPLAY_MODE.RENDERED, label: "Rendered", title: "Shaded material appearance without edge overlay" },
  { value: CAD_DISPLAY_MODE.TRANSPARENT, label: "X-Ray", title: "Transparent solids with visible CAD edges" },
  { value: CAD_DISPLAY_MODE.HIDDEN_EDGES, label: "Hidden", title: "Shaded with hidden edges visible" },
  { value: CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED, label: "Lines", title: "Visible lines with hidden lines removed" },
  { value: CAD_DISPLAY_MODE.UNSHADED, label: "Flat", title: "Unshaded flat color" },
  { value: CAD_DISPLAY_MODE.WIREFRAME, label: "Wire", title: "Full wireframe" }
];

const FLOOR_MODE_OPTIONS = [
  { value: THEME_FLOOR_MODES.STAGE, label: "Stage" },
  { value: THEME_FLOOR_MODES.GRID, label: "Grid" },
  { value: THEME_FLOOR_MODES.NONE, label: "None" }
];

const COLOR_MODE_OPTIONS = [
  { value: THEME_COLOR_MODES.SYSTEM, label: "System" },
  { value: THEME_COLOR_MODES.LIGHT, label: "Light" },
  { value: THEME_COLOR_MODES.DARK, label: "Dark" }
];

const PRIMARY_LIGHT_OPTIONS = [
  { value: "directional", label: "Directional" },
  { value: "spot", label: "Spot" },
  { value: "point", label: "Point" }
];

const fieldLabelClasses = FILE_SHEET_FIELD_LABEL_CLASSES;
const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;
const compactInputClasses = FILE_SHEET_COMPACT_INPUT_CLASSES;
const precisionSliderClasses = FILE_SHEET_PRECISION_SLIDER_CLASSES;
const SLIDER_COMMIT_DELAY_MS = 120;
const AXIS_OPTIONS = Object.freeze(["x", "y", "z"]);
const EDGE_CLASS_CONTROLS = Object.freeze([
  Object.freeze({ id: "feature", label: "Feature", defaultOpacity: 1, defaultThickness: 1.15 }),
  Object.freeze({ id: "tangent", label: "Tangent", defaultOpacity: 0.5, defaultThickness: 1.15 }),
  Object.freeze({ id: "seam", label: "Seam", defaultOpacity: 0.85, defaultThickness: 1.15 }),
  Object.freeze({ id: "degenerate", label: "Degenerate", defaultOpacity: 1, defaultThickness: 0 })
]);

function normalizeEdgeAvailability(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const classes = Array.isArray(value.generatedVisibilityClasses)
    ? value.generatedVisibilityClasses
    : Array.isArray(value.visibilityClasses)
      ? value.visibilityClasses
      : null;
  if (!classes) {
    return null;
  }
  return new Set(classes.map((item) => String(item || "").trim()).filter(Boolean));
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatNumber(value, digits = 2) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "0";
  }
  return numericValue.toFixed(digits);
}

function formatMm(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "0";
  }
  if (Math.abs(numericValue) >= 100) {
    return numericValue.toFixed(0);
  }
  if (Math.abs(numericValue) >= 10) {
    return numericValue.toFixed(1);
  }
  return numericValue.toFixed(2);
}

function Field({ label, value, trailing, children, className, contentClassName }) {
  return (
    <FileSheetControlRow
      label={label}
      value={value}
      trailing={trailing}
      className={className}
      contentClassName={contentClassName}
    >
      {children}
    </FileSheetControlRow>
  );
}

function Section({ title, value, children, ...props }) {
  return (
    <FileSheetSection value={value} title={title} {...props}>
      {children}
    </FileSheetSection>
  );
}

function ControlSubsection({ title, children, className, hideFirstSeparator = true }) {
  return (
    <FileSheetSubsection title={title} className={className} hideFirstSeparator={hideFirstSeparator}>
      {children}
    </FileSheetSubsection>
  );
}

function NestedControlGroup({ title, children, className, contentClassName }) {
  return (
    <FileSheetSubsubsection
      title={title}
      className={className}
      contentClassName={contentClassName}
    >
      {children}
    </FileSheetSubsubsection>
  );
}

function getSliderInputProps(children) {
  try {
    const child = Children.only(children);
    return isValidElement(child) && child.type === SliderInput ? child.props : null;
  } catch {
    return null;
  }
}

function SliderField({ label, value, children, onValueCommit, valueInputProps }) {
  const sliderInputProps = getSliderInputProps(children);
  const commitValue = onValueCommit || (
    sliderInputProps?.onChange ? (nextValue) => {
      sliderInputProps.onChange(parseFileSheetNumberInput(nextValue, {
        fallback: sliderInputProps.value,
        min: sliderInputProps.min,
        max: sliderInputProps.max
      }));
    } : null
  );

  return (
    <FileSheetSliderField
      label={label}
      value={value}
      onValueCommit={commitValue}
      valueInputProps={commitValue ? {
        ariaLabel: `${label} value`,
        ...valueInputProps
      } : valueInputProps}
    >
      {children}
    </FileSheetSliderField>
  );
}

function ThemeToggleRow({ label, checked, onChange, disabled = false, description }) {
  return (
    <FileSheetToggleRow
      label={label}
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      description={description}
    />
  );
}

function SliderInput({ value, min, max, step = 0.01, onChange }) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
  const [draftValue, setDraftValue] = useState(numericValue);
  const commitTimerRef = useRef(null);

  useEffect(() => {
    setDraftValue(numericValue);
  }, [numericValue]);

  useEffect(() => () => {
    if (commitTimerRef.current) {
      clearTimeout(commitTimerRef.current);
    }
  }, []);

  const resolveNextValue = (nextValue) => {
    const numericNextValue = Number(nextValue);
    return Number.isFinite(numericNextValue) ? clamp(numericNextValue, min, max) : numericValue;
  };

  const commitValue = (nextValue) => {
    const resolvedNextValue = resolveNextValue(nextValue);
    if (commitTimerRef.current) {
      clearTimeout(commitTimerRef.current);
    }
    if (Math.abs(resolvedNextValue - numericValue) > 1e-9) {
      onChange(resolvedNextValue);
    }
  };

  const scheduleCommitValue = (nextValue) => {
    const resolvedNextValue = resolveNextValue(nextValue);
    setDraftValue(resolvedNextValue);
    if (commitTimerRef.current) {
      clearTimeout(commitTimerRef.current);
    }
    commitTimerRef.current = setTimeout(() => {
      commitValue(resolvedNextValue);
    }, SLIDER_COMMIT_DELAY_MS);
  };

  return (
    <Slider
      value={[draftValue]}
      min={min}
      max={max}
      step={step}
      onValueChange={(nextValue) => scheduleCommitValue(nextValue[0] ?? draftValue)}
      onValueCommit={(nextValue) => commitValue(nextValue[0] ?? draftValue)}
      className={precisionSliderClasses}
    />
  );
}

function EdgeClassControlRow({
  label,
  checked,
  available = true,
  thickness,
  opacity,
  onEnabledChange,
  onThicknessChange,
  onOpacityChange
}) {
  return (
    <NestedControlGroup
      title={label}
      className="py-2"
      contentClassName="space-y-3"
    >
      <ThemeToggleRow
        label="Enabled"
        checked={checked && available}
        onChange={onEnabledChange}
        disabled={!available}
        description={available ? undefined : "Not generated for this file"}
      />
      {checked && available ? (
        <>
          <SliderField label="Thickness" value={`${formatNumber(thickness, 2)} px`}>
            <SliderInput
              value={thickness}
              min={0}
              max={2}
              step={0.05}
              onChange={onThicknessChange}
            />
          </SliderField>
          <SliderField label="Opacity" value={formatNumber(opacity)}>
            <SliderInput
              value={opacity}
              min={0}
              max={1}
              step={0.01}
              onChange={onOpacityChange}
            />
          </SliderField>
        </>
      ) : null}
    </NestedControlGroup>
  );
}

function HighlightEdgeSlidersRow({
  thickness,
  opacity,
  onThicknessChange,
  onOpacityChange
}) {
  return (
    <>
      <SliderField label="Width" value={`${formatNumber(thickness, 1)} px`}>
        <SliderInput
          value={thickness}
          min={2}
          max={4}
          step={0.1}
          onChange={onThicknessChange}
        />
      </SliderField>
      <SliderField label="Opacity" value={formatNumber(opacity)}>
        <SliderInput
          value={opacity}
          min={0}
          max={1}
          step={0.01}
          onChange={onOpacityChange}
        />
      </SliderField>
    </>
  );
}

function ColorInput({
  value,
  onChange,
  className,
  swatchClassName,
  valueClassName,
  showValue = true,
  disabled = false,
  ...props
}) {
  return (
    <ColorPicker
      value={value}
      onChange={onChange}
      className={cn(
        compactInputClasses,
        "w-fit justify-start gap-1.5 px-1.5",
        className
      )}
      swatchClassName={cn("size-3.5", swatchClassName)}
      valueClassName={valueClassName}
      popoverAlign="end"
      showValue={showValue}
      disabled={disabled}
      {...props}
    />
  );
}

function ColorField({ label, value, onChange, className, labelClassName }) {
  return (
    <FileSheetControlRow
      label={label}
      trailing={(
        <ColorInput
          value={value}
          onChange={onChange}
        />
      )}
      className={className}
      labelClassName={labelClassName}
    />
  );
}

function getPathValue(source, path) {
  return path.reduce((value, key) => (
    value && typeof value === "object" ? value[key] : undefined
  ), source);
}

function setPathValue(target, path, value) {
  let cursor = target;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    if (!cursor[key] || typeof cursor[key] !== "object" || Array.isArray(cursor[key])) {
      cursor[key] = {};
    }
    cursor = cursor[key];
  }
  cursor[path[path.length - 1]] = value;
}

function cloneModeColors(modeColors = {}) {
  return {
    light: JSON.parse(JSON.stringify(modeColors.light || {})),
    dark: JSON.parse(JSON.stringify(modeColors.dark || {}))
  };
}

function activeThemeColorMode(themeSettings = {}, resolvedColorSchemeMode = THEME_COLOR_MODES.LIGHT) {
  if (themeSettings.colorMode === THEME_COLOR_MODES.DARK) {
    return THEME_COLOR_MODES.DARK;
  }
  if (themeSettings.colorMode === THEME_COLOR_MODES.LIGHT) {
    return THEME_COLOR_MODES.LIGHT;
  }
  return resolvedColorSchemeMode === THEME_COLOR_MODES.DARK
    ? THEME_COLOR_MODES.DARK
    : THEME_COLOR_MODES.LIGHT;
}

function themeModeColorValue(themeSettings = {}, path = [], mode = THEME_COLOR_MODES.LIGHT) {
  return getPathValue(themeSettings.modeColors?.[mode], path) ||
    getPathValue(themeSettings, path) ||
    "#ffffff";
}

function ColorModeIndicatorLabel({ label, mode }) {
  const isDarkMode = mode === THEME_COLOR_MODES.DARK;
  const ModeIcon = isDarkMode ? Moon : Sun;
  const modeLabel = isDarkMode ? "dark" : "light";
  return (
    <span className="inline-flex max-w-full items-center gap-1 align-bottom" title={`Uses the ${modeLabel} mode color`}>
      <span className="min-w-0 truncate">{label}</span>
      <ModeIcon className="size-2.5 shrink-0 text-muted-foreground/70" strokeWidth={2.25} aria-hidden="true" />
      <span className="sr-only">{`Uses the ${modeLabel} mode color`}</span>
    </span>
  );
}

function ColorModeField({
  label,
  path,
  themeSettings,
  onChange,
  resolvedColorSchemeMode = THEME_COLOR_MODES.LIGHT
}) {
  const colorMode = themeSettings.colorMode || THEME_COLOR_MODES.SYSTEM;
  const mode = activeThemeColorMode(themeSettings, resolvedColorSchemeMode);
  if (colorMode === THEME_COLOR_MODES.SYSTEM) {
    return (
      <ColorField
        label={<ColorModeIndicatorLabel label={label} mode={mode} />}
        value={themeModeColorValue(themeSettings, path, mode)}
        onChange={(nextValue) => onChange(path, nextValue, mode)}
      />
    );
  }

  return (
    <ColorField
      label={label}
      value={themeModeColorValue(themeSettings, path, mode)}
      onChange={(nextValue) => onChange(path, nextValue)}
    />
  );
}

function resolveFillColors(materials = {}) {
  const colors = Array.isArray(materials.fillColors) && materials.fillColors.length
    ? materials.fillColors
    : [materials.defaultColor || "#ffffff"];
  return colors.slice(0, MAX_THEME_FILL_COLORS);
}

function settingsSignature(settings) {
  return JSON.stringify(normalizeThemeSettings(settings));
}

function FillColorEditor({ colors, onChange, cycleColors = false }) {
  const resolvedColors = colors.length ? colors : ["#ffffff"];
  const commitColors = (nextColors) => {
    const compactColors = nextColors.filter(Boolean).slice(0, MAX_THEME_FILL_COLORS);
    onChange(compactColors.length ? compactColors : [resolvedColors[0] || "#ffffff"]);
  };

  return (
    <div
      className="flex flex-wrap justify-start gap-1.5"
      data-cad-fill-color-grid="true"
    >
      {resolvedColors.map((color, index) => (
        <div
          key={index}
          className={cn(
            "group relative transition-opacity",
            !cycleColors && index > 0 && "opacity-45 grayscale"
          )}
        >
          <ColorInput
            value={color}
            swatchClassName="size-3.5"
            onChange={(nextColor) => {
              const nextColors = [...resolvedColors];
              nextColors[index] = nextColor;
              commitColors(nextColors);
            }}
            aria-label={`Fill color ${index + 1}`}
            title={`Fill color ${index + 1}: ${color}`}
          />
          {resolvedColors.length > 1 ? (
            <Button
              type="button"
              variant="outline"
              size="icon-xs"
              className="absolute -right-1.5 -top-1.5 z-10 size-4 rounded-full border-border !bg-[rgb(245_247_250)] p-0 text-muted-foreground shadow-xs hover:!bg-[rgb(245_247_250)] hover:text-foreground dark:!bg-[rgb(12_15_22)] dark:hover:!bg-[rgb(12_15_22)]"
              onClick={() => commitColors(resolvedColors.filter((_, colorIndex) => colorIndex !== index))}
              aria-label={`Remove color ${index + 1}`}
              title={`Remove color ${index + 1}`}
            >
              <X className="h-2.5 w-2.5" strokeWidth={2.25} aria-hidden="true" />
            </Button>
          ) : null}
        </div>
      ))}
      {resolvedColors.length < MAX_THEME_FILL_COLORS ? (
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          className="size-7 rounded-md p-0 text-muted-foreground hover:text-foreground"
          onClick={() => commitColors([...resolvedColors, resolvedColors[resolvedColors.length - 1] || "#ffffff"])}
          aria-label="Add fill color"
          title="Add fill color"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}

function SegmentedControl({ value, onChange, options }) {
  const columnCount = Math.max(1, Math.min(options.length, options.length > 4 ? 3 : 4));
  const templateColumns = `repeat(${columnCount}, minmax(0, 1fr))`;
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(nextValue) => {
        if (!nextValue) {
          return;
        }
        onChange(nextValue);
      }}
      className="grid min-h-7 w-full min-w-0 auto-rows-[1.75rem]"
      style={{ gridTemplateColumns: templateColumns }}
    >
      {options.map((option) => {
        const Icon = option.Icon;
        const disabled = option.disabled === true;
        return (
          <ToggleGroupItem
            key={option.value}
            value={option.value}
            disabled={disabled}
            className={cn("min-w-0 gap-1.5 !h-7 px-1.5 text-[11px]", FILE_SHEET_SEGMENTED_ITEM_CLASSES)}
            title={option.title || option.label}
            aria-label={option.label}
          >
            {Icon ? <Icon className="size-3" strokeWidth={2} aria-hidden="true" /> : null}
            <span className="truncate">{option.label}</span>
          </ToggleGroupItem>
        );
      })}
    </ToggleGroup>
  );
}

export function PresetSwatch({ preset = null }) {
  if (!preset) {
    return (
      <span
        className="h-4 w-8 shrink-0 rounded-md border border-dashed bg-muted"
        aria-hidden="true"
      />
    );
  }

  return (
    <span
      className="relative h-4 w-8 shrink-0 overflow-hidden rounded-md border shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12)]"
      style={{ background: preset.preview.background }}
      aria-hidden="true"
    >
      <span
        className="absolute inset-y-0 right-0 w-3"
        style={{ backgroundColor: preset.preview.accentColor, opacity: 0.9 }}
      />
    </span>
  );
}

export function useSystemDefaultThemePresetId() {
  const [systemDefaultPresetId, setSystemDefaultPresetId] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return DEFAULT_THEME_PRESET_ID;
    }
    return resolveSystemThemePresetId({
      prefersDark: window.matchMedia("(prefers-color-scheme: dark)").matches === true
    });
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }

    const colorSchemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const updateSystemDefaultPreset = () => {
      setSystemDefaultPresetId(resolveSystemThemePresetId({
        prefersDark: colorSchemeQuery.matches === true
      }));
    };

    updateSystemDefaultPreset();
    colorSchemeQuery.addEventListener?.("change", updateSystemDefaultPreset);
    return () => {
      colorSchemeQuery.removeEventListener?.("change", updateSystemDefaultPreset);
    };
  }, []);

  return systemDefaultPresetId;
}

function orderedThemePresets(presets, systemDefaultPresetId) {
  const defaultPresetIndex = presets.findIndex((preset) => preset.id === systemDefaultPresetId);
  if (defaultPresetIndex <= 0) {
    return presets;
  }
  return [
    presets[defaultPresetIndex],
    ...presets.slice(0, defaultPresetIndex),
    ...presets.slice(defaultPresetIndex + 1)
  ];
}

function resolveActiveThemePreset(themePresets, themePresetId, themeSettings) {
  const directPreset = themePresets.find((preset) => preset.id === themePresetId) || null;
  if (directPreset) {
    return directPreset;
  }
  const currentThemeSettingsSignature = settingsSignature(themeSettings);
  return themePresets.find((preset) => settingsSignature(preset.settings) === currentThemeSettingsSignature) || null;
}

function themeSettingsChangedFromPreset(preset, themeSettings) {
  return !preset || settingsSignature(preset.settings) !== settingsSignature(themeSettings);
}

function themePresetIsCustom(preset) {
  return String(preset?.id || "").startsWith("custom:");
}

function themePresetCanResetToDefault(preset) {
  const presetId = normalizeThemePresetId(preset?.presetId || preset?.id);
  return Boolean(
    themePresetIsCustom(preset) &&
    presetId &&
    settingsSignature(preset.settings) !== settingsSignature(cloneThemePresetSettings(presetId))
  );
}

function themePresetCanUpdate(preset) {
  return themePresetIsCustom(preset);
}

function themePresetCanDelete(preset) {
  return themePresetIsCustom(preset);
}

function themeLibraryChangedFromDefaults(themePresets = []) {
  if (!Array.isArray(themePresets) || !themePresets.length) {
    return false;
  }
  if (themePresets.length !== THEME_PRESETS.length) {
    return true;
  }
  for (let index = 0; index < THEME_PRESETS.length; index += 1) {
    const defaultPreset = THEME_PRESETS[index];
    const theme = themePresets[index];
    if (!theme || theme.id !== defaultPreset.id || theme.label !== defaultPreset.label) {
      return true;
    }
    if (normalizeThemePresetId(theme.presetId || theme.id) !== defaultPreset.id) {
      return true;
    }
    if (settingsSignature(theme.settings) !== settingsSignature(defaultPreset.settings)) {
      return true;
    }
  }
  return false;
}

function ThemeDirtyIndicator({ className }) {
  return (
    <span
      aria-hidden="true"
      className={cn("h-2 w-2 shrink-0 rounded-full bg-blue-500", className)}
    />
  );
}

function ThemePresetOverflowMenu({
  preset,
  canDeleteTheme,
  canResetToDefault,
  onActionActiveChange,
  onDelete,
  onEdit,
  onReset
}) {
  const [open, setOpen] = useState(false);
  const label = String(preset?.label || "theme").trim() || "theme";
  const actionsLabel = `Theme actions for ${label}`;

  const setActionActive = (nextActive) => {
    onActionActiveChange?.(nextActive);
  };

  const handleOpenChange = (nextOpen) => {
    setOpen(nextOpen);
    setActionActive(nextOpen);
  };

  const stopMenuPropagation = (event) => {
    event.stopPropagation();
  };
  const handleActionSelect = (event, action) => {
    event.preventDefault();
    event.stopPropagation();
    setActionActive(false);
    action?.();
  };

  const handleTriggerBlur = (event) => {
    if (!open && !event.currentTarget.contains(event.relatedTarget)) {
      setActionActive(false);
    }
  };

  return (
    <DropdownMenuSub open={open} onOpenChange={handleOpenChange}>
      <DropdownMenuSubTrigger
        showChevron={false}
        data-theme-menu-action=""
        aria-label={actionsLabel}
        title={actionsLabel}
        className={cn(
          "theme-preset-overflow-trigger flex size-7 shrink-0 items-center justify-center rounded-md p-0",
          "text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
          "focus:bg-accent focus:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        )}
        onPointerEnter={() => setActionActive(true)}
        onPointerLeave={() => {
          if (!open) {
            setActionActive(false);
          }
        }}
        onFocus={() => setActionActive(true)}
        onBlur={handleTriggerBlur}
        onMouseDown={stopMenuPropagation}
        onPointerDown={stopMenuPropagation}
        onKeyDown={stopMenuPropagation}
      >
        <MoreHorizontal className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent sideOffset={6} className="w-40">
        <DropdownMenuItem
          className="gap-2 text-xs"
          onSelect={(event) => handleActionSelect(event, onEdit)}
        >
          <Pencil className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
          <span>Edit</span>
        </DropdownMenuItem>
        {canResetToDefault ? (
          <DropdownMenuItem
            className="gap-2 text-xs"
            onSelect={(event) => handleActionSelect(event, onReset)}
          >
            <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
            <span>Reset to preset</span>
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          disabled={!canDeleteTheme}
          className="gap-2 text-xs"
          onSelect={(event) => handleActionSelect(event, canDeleteTheme ? onDelete : null)}
        >
          <Trash2 className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
          <span>Delete</span>
        </DropdownMenuItem>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

function ThemeWarningDialog({
  open,
  onOpenChange,
  title,
  description,
  actionLabel,
  onConfirm
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="sm:max-w-sm">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-white hover:bg-destructive/90"
            onClick={onConfirm}
          >
            {actionLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function SaveThemeDialog({
  defaultName,
  onOpenChange,
  onSave,
  open
}) {
  const inputId = useId();
  const [draftName, setDraftName] = useState(defaultName);
  const normalizedDraftName = draftName.trim();

  useEffect(() => {
    if (open) {
      setDraftName(defaultName);
    }
  }, [defaultName, open]);

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!normalizedDraftName || typeof onSave !== "function") {
      return;
    }
    const savedPreset = onSave(normalizedDraftName);
    if (savedPreset) {
      onOpenChange?.(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-5 sm:max-w-sm">
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <DialogHeader className="gap-1.5">
            <DialogTitle className="text-base">Save Theme</DialogTitle>
            <DialogDescription className="sr-only">
              Enter a name for this theme.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <label className={fieldLabelClasses} htmlFor={inputId}>
              Theme name
            </label>
            <Input
              id={inputId}
              value={draftName}
              autoFocus
              onChange={(event) => setDraftName(event.target.value)}
            />
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={!normalizedDraftName}>
              Save theme
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ThemePresetDropdown({
  themePresets = [],
  themeSettings,
  themePresetId = "",
  updateThemeSettings,
  handleDeleteCustomThemePreset,
  handleEditThemePreset,
  handleResetThemePresetToDefault,
  handleRestoreDefaultThemePresets,
  triggerClassName,
  iconClassName
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [deleteThemeId, setDeleteThemeId] = useState("");
  const [resetThemeId, setResetThemeId] = useState("");
  const [restoreThemesDialogOpen, setRestoreThemesDialogOpen] = useState(false);
  const [activeActionThemeId, setActiveActionThemeId] = useState("");
  const systemDefaultPresetId = useSystemDefaultThemePresetId();
  const orderedPresets = useMemo(
    () => orderedThemePresets(themePresets, systemDefaultPresetId),
    [themePresets, systemDefaultPresetId]
  );
  const activeThemePreset = useMemo(
    () => resolveActiveThemePreset(themePresets, themePresetId, themeSettings),
    [themePresets, themePresetId, themeSettings]
  );
  const activeThemePresetId = activeThemePreset?.id || "";
  const activeThemeLabel = activeThemePreset?.label || "Theme";
  const deleteThemePreset = themePresets.find((preset) => preset.id === deleteThemeId) || null;
  const resetThemePreset = themePresets.find((preset) => preset.id === resetThemeId) || null;
  const themeLibraryHasChanged = useMemo(
    () => themeLibraryChangedFromDefaults(themePresets),
    [themePresets]
  );

  const handleMenuOpenChange = (nextOpen) => {
    setMenuOpen(nextOpen);
    if (!nextOpen) {
      setActiveActionThemeId("");
    }
  };

  const clearThemeMenuActionState = (presetId) => {
    setActiveActionThemeId((currentThemeId) => (
      currentThemeId === presetId ? "" : currentThemeId
    ));
  };

  const applyThemePreset = (presetId) => {
    const preset = themePresets.find((candidate) => candidate.id === presetId);
    if (!preset) {
      return;
    }
    updateThemeSettings?.(preset.settings, {
      persistGlobal: true,
      presetId: preset.id
    });
  };

  const handleDeleteThemePreset = (presetId) => {
    const preset = themePresets.find((candidate) => candidate.id === presetId);
    if (themePresetCanDelete(preset) && typeof handleDeleteCustomThemePreset === "function") {
      setDeleteThemeId(presetId);
      setMenuOpen(false);
    }
  };

  const handleConfirmDeleteTheme = () => {
    if (deleteThemePreset && typeof handleDeleteCustomThemePreset === "function") {
      handleDeleteCustomThemePreset(deleteThemePreset.id);
    }
    setDeleteThemeId("");
  };

  const handleEditTheme = (presetId) => {
    const didEdit = typeof handleEditThemePreset === "function"
      ? handleEditThemePreset(presetId)
      : false;
    if (!didEdit) {
      applyThemePreset(presetId);
    }
    setMenuOpen(false);
  };

  const handleResetThemePreset = (presetId) => {
    setResetThemeId(presetId);
    setMenuOpen(false);
  };

  const handleConfirmResetTheme = () => {
    if (resetThemePreset && typeof handleResetThemePresetToDefault === "function") {
      handleResetThemePresetToDefault(resetThemePreset.id);
    }
    setResetThemeId("");
  };

  const handleConfirmRestoreThemes = () => {
    if (typeof handleRestoreDefaultThemePresets === "function") {
      handleRestoreDefaultThemePresets();
    }
    setRestoreThemesDialogOpen(false);
  };

  return (
    <>
      <DropdownMenu open={menuOpen} onOpenChange={handleMenuOpenChange}>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Theme: ${activeThemeLabel}`}
            title={`Theme: ${activeThemeLabel}`}
            className={triggerClassName}
          >
            <Contrast className={iconClassName} strokeWidth={2} aria-hidden="true" />
            <span className="sr-only">Theme</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={6} className="w-64">
          <DropdownMenuLabel className="px-2 py-1.5 text-xs text-muted-foreground">
            Theme
          </DropdownMenuLabel>
          {orderedPresets.map((preset) => {
            const active = preset.id === activeThemePresetId;
            const canResetToDefault = themePresetCanResetToDefault(preset);
            const canDeleteTheme = themePresetCanDelete(preset);
            const actionActive = activeActionThemeId === preset.id;
            return (
              <div
                key={preset.id}
                data-active={active ? "true" : undefined}
                data-action-hover={actionActive ? "true" : undefined}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "theme-preset-menu-item flex min-w-0 items-center gap-1 rounded-sm text-xs"
                )}
              >
                <DropdownMenuItem
                  className={cn(
                    "theme-preset-menu-row min-w-0 flex-1 gap-2 px-2 py-1.5 text-xs",
                    active && "font-semibold"
                  )}
                  data-theme-menu-row-surface=""
                  onSelect={() => applyThemePreset(preset.id)}
                >
                  <PresetSwatch preset={preset} />
                  <span className="min-w-0 flex-1 truncate">{preset.label}</span>
                  {preset.id === systemDefaultPresetId ? (
                    <span
                      className="rounded-full border px-1.5 py-0.5 text-[9px] uppercase text-muted-foreground"
                      data-theme-menu-default-badge=""
                    >
                      Default
                    </span>
                  ) : null}
                </DropdownMenuItem>
                <span
                  className="theme-preset-menu-actions ml-auto flex shrink-0 items-center gap-0.5 rounded-sm px-0.5 py-0.5"
                >
                  <ThemePresetOverflowMenu
                    preset={preset}
                    canDeleteTheme={canDeleteTheme}
                    canResetToDefault={canResetToDefault}
                    onActionActiveChange={(nextActive) => {
                      if (nextActive) {
                        setActiveActionThemeId(preset.id);
                      } else {
                        clearThemeMenuActionState(preset.id);
                      }
                    }}
                    onEdit={() => handleEditTheme(preset.id)}
                    onReset={() => handleResetThemePreset(preset.id)}
                    onDelete={() => handleDeleteThemePreset(preset.id)}
                  />
                </span>
              </div>
            );
          })}
          {themeLibraryHasChanged ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-xs"
                onSelect={(event) => {
                  event.preventDefault();
                  setRestoreThemesDialogOpen(true);
                  setMenuOpen(false);
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                <span>Restore defaults</span>
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      <ThemeWarningDialog
        open={Boolean(deleteThemePreset)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            setDeleteThemeId("");
          }
        }}
        title="Delete Theme"
        description={`Delete ${deleteThemePreset?.label || "this theme"}? This removes it from your theme list.`}
        actionLabel="Delete theme"
        onConfirm={handleConfirmDeleteTheme}
      />
      <ThemeWarningDialog
        open={Boolean(resetThemePreset)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            setResetThemeId("");
          }
        }}
        title="Reset Theme"
        description={`Reset ${resetThemePreset?.label || "this theme"} to its built-in preset settings?`}
        actionLabel="Reset theme"
        onConfirm={handleConfirmResetTheme}
      />
      <ThemeWarningDialog
        open={restoreThemesDialogOpen}
        onOpenChange={setRestoreThemesDialogOpen}
        title="Restore Defaults"
        description="This clears saved theme changes, removes saved themes, and restores deleted presets."
        actionLabel="Restore defaults"
        onConfirm={handleConfirmRestoreThemes}
      />
    </>
  );
}

function ThemeAppearanceSection({
  themePresets = [],
  themeSettings,
  themePresetId = "",
  updateThemeSettings,
  handleResetThemeSettings,
  handleSaveCustomThemePreset,
  handleUpdateThemePresetSettings,
  showEdgeSettings = true,
  edgeAvailability = null
}) {
  const [saveThemeDialogOpen, setSaveThemeDialogOpen] = useState(false);
  const activeThemePreset = useMemo(
    () => resolveActiveThemePreset(themePresets, themePresetId, themeSettings),
    [themePresets, themePresetId, themeSettings]
  );
  const activeThemeId = activeThemePreset?.id || "";
  const canUpdateActiveTheme = themePresetCanUpdate(activeThemePreset);
  const themeHasChanged = themeSettingsChangedFromPreset(activeThemePreset, themeSettings);
  const fallbackThemeName = activeThemePreset?.label
    ? `${activeThemePreset.label} copy`
    : "Theme copy";
  const colorMode = themeSettings.colorMode || THEME_COLOR_MODES.SYSTEM;

  const applyThemePreset = (presetId) => {
    const preset = themePresets.find((candidate) => candidate.id === presetId);
    if (!preset) {
      return;
    }
    updateThemeSettings?.(preset.settings, {
      persistGlobal: true,
      presetId: preset.id
    });
  };

  const handleSaveTheme = (themeName) => {
    if (!themeHasChanged || typeof handleSaveCustomThemePreset !== "function") {
      return null;
    }
    return handleSaveCustomThemePreset(themeName);
  };

  const handleUpdateTheme = () => {
    if (!themeHasChanged || !activeThemeId || !canUpdateActiveTheme || typeof handleUpdateThemePresetSettings !== "function") {
      return;
    }
    handleUpdateThemePresetSettings(activeThemeId);
  };

  const handleColorModeChange = (nextColorMode) => {
    updateThemeSettings?.((current) => ({
      ...normalizeThemeSettings(current),
      colorMode: nextColorMode
    }));
  };

  return (
    <>
      <ControlSubsection title="Theme">
        <Field
          label="Current"
          value={themeHasChanged ? "Changed" : "Saved"}
        >
          <Select value={activeThemeId} onValueChange={applyThemePreset}>
            <SelectTrigger
              size="sm"
              className={cn(compactInputClasses, "w-full justify-between")}
              aria-label="Theme"
            >
              <span className="flex min-w-0 items-center gap-2">
                <PresetSwatch preset={activeThemePreset} />
                <span className="min-w-0 truncate">{activeThemePreset?.label || "Theme"}</span>
              </span>
            </SelectTrigger>
            <SelectContent>
              {themePresets.map((preset) => (
                <SelectItem key={preset.id} value={preset.id} className="text-xs">
                  <PresetSwatch preset={preset} />
                  <span className="min-w-0 truncate">{preset.label}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field label="Color mode">
          <SegmentedControl
            value={colorMode}
            options={COLOR_MODE_OPTIONS}
            onChange={handleColorModeChange}
          />
        </Field>

        <FileSheetControlRow>
          <div className="flex flex-wrap gap-1.5">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={cn(compactButtonClasses, "relative", themeHasChanged ? "pr-5" : null)}
              disabled={!themeHasChanged || typeof handleSaveCustomThemePreset !== "function"}
              onClick={() => setSaveThemeDialogOpen(true)}
            >
              <span>Save as</span>
              {themeHasChanged ? (
                <ThemeDirtyIndicator className="absolute right-1.5 top-1.5 h-1.5 w-1.5" />
              ) : null}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={compactButtonClasses}
              disabled={!themeHasChanged || !activeThemeId || !canUpdateActiveTheme || typeof handleUpdateThemePresetSettings !== "function"}
              onClick={handleUpdateTheme}
            >
              <span>Update</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={compactButtonClasses}
              disabled={!themeHasChanged || !activeThemeId || typeof handleResetThemeSettings !== "function"}
              onClick={() => handleResetThemeSettings?.()}
            >
              <RotateCcw className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
              <span>Restore to default</span>
            </Button>
          </div>
        </FileSheetControlRow>
      </ControlSubsection>
      <SaveThemeDialog
        defaultName={fallbackThemeName}
        onOpenChange={setSaveThemeDialogOpen}
        onSave={handleSaveTheme}
        open={saveThemeDialogOpen}
      />
    </>
  );
}

function PositionPad({ value, onChange }) {
  const resolvedX = Number.isFinite(Number(value?.x)) ? Number(value.x) : 0;
  const resolvedZ = Number.isFinite(Number(value?.z)) ? Number(value.z) : 0;
  const [draftPosition, setDraftPosition] = useState({ x: resolvedX, z: resolvedZ });
  const draftPositionRef = useRef(draftPosition);
  const commitTimerRef = useRef(null);
  const x = draftPosition.x;
  const z = draftPosition.z;

  useEffect(() => {
    const nextPosition = { x: resolvedX, z: resolvedZ };
    draftPositionRef.current = nextPosition;
    setDraftPosition(nextPosition);
  }, [resolvedX, resolvedZ]);

  useEffect(() => () => {
    if (commitTimerRef.current) {
      clearTimeout(commitTimerRef.current);
    }
  }, []);

  const extent = useMemo(() => {
    const magnitude = Math.max(Math.abs(x), Math.abs(z), 220);
    return Math.min(5000, Math.ceil((magnitude * 1.2) / 20) * 20);
  }, [x, z]);

  const markerLeft = ((x + extent) / (extent * 2)) * 100;
  const markerTop = ((extent - z) / (extent * 2)) * 100;

  const commitPosition = (nextX, nextZ) => {
    if (commitTimerRef.current) {
      clearTimeout(commitTimerRef.current);
    }
    if (nextX !== resolvedX) {
      onChange("x", nextX);
    }
    if (nextZ !== resolvedZ) {
      onChange("z", nextZ);
    }
  };

  const scheduleCommitPosition = (nextX, nextZ) => {
    const nextPosition = { x: nextX, z: nextZ };
    draftPositionRef.current = nextPosition;
    setDraftPosition(nextPosition);
    if (commitTimerRef.current) {
      clearTimeout(commitTimerRef.current);
    }
    commitTimerRef.current = setTimeout(() => {
      commitPosition(nextX, nextZ);
    }, SLIDER_COMMIT_DELAY_MS);
  };

  const updateFromPointer = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return;
    }
    const ratioX = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    const ratioY = clamp((event.clientY - rect.top) / rect.height, 0, 1);
    const nextX = Math.round((ratioX * 2 - 1) * extent);
    const nextZ = Math.round((1 - ratioY * 2) * extent);
    scheduleCommitPosition(nextX, nextZ);
  };

  return (
    <div className="space-y-2">
      <div
        className="relative h-28 w-full touch-none overflow-hidden rounded-md border bg-background"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          updateFromPointer(event);
        }}
        onPointerMove={(event) => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
            return;
          }
          updateFromPointer(event);
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
          commitPosition(draftPositionRef.current.x, draftPositionRef.current.z);
        }}
      >
        <div
          className="absolute inset-0 opacity-45"
          style={{
            backgroundImage: "radial-gradient(circle, rgba(154, 169, 188, 0.65) 1.5px, transparent 1.5px)",
            backgroundSize: "22px 22px"
          }}
          aria-hidden="true"
        />
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" aria-hidden="true" />
        <div className="absolute inset-y-0 left-1/2 w-px bg-border" aria-hidden="true" />
        <div
          className="absolute size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary bg-foreground shadow-xs"
          style={{ left: `${markerLeft}%`, top: `${markerTop}%` }}
          aria-hidden="true"
        />
      </div>
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>X {Math.round(x)}</span>
        <span>Z {Math.round(z)}</span>
        <span>range +/-{extent}</span>
      </div>
    </div>
  );
}

export function DisplaySettingsSection({
  displaySettings,
  updateDisplaySettings,
  clipBounds = null,
  showClip = false
}) {
  const normalizedDisplaySettings = useMemo(
    () => normalizeDisplaySettings(displaySettings),
    [displaySettings]
  );
  const normalizedClipSettings = useMemo(
    () => normalizeStepClipSettings(normalizedDisplaySettings.clip),
    [normalizedDisplaySettings.clip]
  );
  const setDisplay = (patch) => {
    updateDisplaySettings?.((current) => ({
      ...normalizeDisplaySettings(current),
      ...patch
    }));
  };
  const setClip = (patch) => {
    updateDisplaySettings?.((current) => {
      const currentSettings = normalizeDisplaySettings(current);
      return {
        ...currentSettings,
        clip: buildStepClipPatch(currentSettings.clip, patch)
      };
    });
  };
  const updateClipAxisOffset = (axis, nextOffset) => {
    const numericOffset = Number(nextOffset);
    const resolvedOffset = Number.isFinite(numericOffset) ? numericOffset : 0;
    setClip({
      axis,
      offset: resolvedOffset,
      offsets: { [axis]: resolvedOffset },
      enabled: resolvedOffset > 0
    });
  };

  return (
    <Section title="Display" value="display">
      <Field label="Mode">
        <Select
          value={normalizedDisplaySettings.mode}
          onValueChange={(nextValue) => setDisplay({ mode: nextValue })}
        >
          <SelectTrigger size="sm" className="h-7 !text-[11px]" aria-label="Display mode">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DISPLAY_MODE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value} className="text-xs" title={option.title}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      {showClip ? (
        <ControlSubsection title="Clip" hideFirstSeparator={false}>
          {AXIS_OPTIONS.map((axis) => {
            const axisOffset = normalizedClipSettings.offsets?.[axis] ?? DEFAULT_STEP_CLIP_SETTINGS.offsets[axis];
            const axisSettings = {
              ...normalizedClipSettings,
              axis,
              offset: axisOffset,
              offsets: {
                ...normalizedClipSettings.offsets,
                [axis]: axisOffset
              }
            };
            const boundsForAxis = clipAxisBounds(clipBounds, axis);
            const axisRange = Math.max(boundsForAxis.max - boundsForAxis.min, 0);
            const clipPosition = clipAxisPosition(clipBounds, axisSettings);
            return (
              <FileSheetSliderField
                key={axis}
                label={axis}
                value={`${formatMm(clipPosition)} mm`}
                onValueCommit={(nextValue) => {
                  const nextPosition = parseFileSheetNumberInput(nextValue, {
                    fallback: clipPosition,
                    min: boundsForAxis.min,
                    max: boundsForAxis.max
                  });
                  updateClipAxisOffset(
                    axis,
                    axisRange > 0 ? (nextPosition - boundsForAxis.min) / axisRange : axisOffset
                  );
                }}
                valueInputProps={{
                  disabled: !axisRange,
                  ariaLabel: `Clip ${axis.toUpperCase()} position`
                }}
              >
                <Slider
                  className={precisionSliderClasses}
                  value={[axisOffset]}
                  min={0}
                  max={1}
                  step={0.001}
                  disabled={!axisRange}
                  onValueChange={(value) => {
                    const nextOffset = Array.isArray(value) ? value[0] : value;
                    updateClipAxisOffset(axis, nextOffset);
                  }}
                  aria-label={`Clip ${axis.toUpperCase()} axis`}
                />
                <div className="mt-1 flex justify-between text-[10px] text-[var(--ui-text-muted)]">
                  <span>{formatMm(boundsForAxis.min)}</span>
                  <span>{formatMm(boundsForAxis.max)}</span>
                </div>
              </FileSheetSliderField>
            );
          })}

          <FileSheetControlRow>
            <div className="flex flex-wrap gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={compactButtonClasses}
                onClick={() => setClip({ invert: !normalizedClipSettings.invert })}
                aria-pressed={normalizedClipSettings.invert}
                title="Flip clip side"
              >
                <FlipHorizontal2 className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                <span>Flip</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={compactButtonClasses}
                onClick={() => setDisplay({ clip: normalizeStepClipSettings(DEFAULT_STEP_CLIP_SETTINGS) })}
                title="Reset clip plane"
              >
                <RotateCcw className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                <span>Reset</span>
              </Button>
            </div>
          </FileSheetControlRow>
        </ControlSubsection>
      ) : null}
    </Section>
  );
}

export function ThemeSettingsSections({
  themePresets = [],
  themeSettings,
  themePresetId = "",
  resolvedColorSchemeMode = THEME_COLOR_MODES.LIGHT,
  updateThemeSettings,
  handleResetThemeSettings,
  handleSaveCustomThemePreset,
  handleUpdateThemePresetSettings,
  showEdgeSettings = true,
  edgeAvailability = null
}) {
  const [activePrimaryLight, setActivePrimaryLight] = useState("directional");
  const activeThemePreset = useMemo(
    () => resolveActiveThemePreset(themePresets, themePresetId, themeSettings),
    [themePresets, themePresetId, themeSettings]
  );
  const themeHasChanged = themeSettingsChangedFromPreset(activeThemePreset, themeSettings);
  const showEdgeDetailControls = showEdgeSettings && themeSettings.edges.enabled;
  const availableEdgeClassSet = useMemo(() => normalizeEdgeAvailability(edgeAvailability), [edgeAvailability]);
  const appearanceTitle = (
    <span className="flex min-w-0 items-center gap-2">
      <span>Appearance</span>
      {themeHasChanged ? <ThemeDirtyIndicator className="h-1.5 w-1.5" /> : null}
    </span>
  );

  const setMaterials = (patch) => {
    updateThemeSettings((current) => ({
      ...current,
      materials: {
        ...current.materials,
        ...patch
      }
    }));
  };

  const setBackground = (patch) => {
    updateThemeSettings((current) => ({
      ...current,
      background: {
        ...current.background,
        ...patch
      }
    }));
  };

  const setFloor = (patch) => {
    updateThemeSettings((current) => ({
      ...current,
      floor: {
        ...current.floor,
        ...patch
      }
    }));
  };

  const setEdges = (patch) => {
    updateThemeSettings((current) => ({
      ...current,
      edges: {
        ...current.edges,
        ...patch
      }
    }));
  };

  const setEdgeClass = (classId, patch) => {
    updateThemeSettings((current) => ({
      ...current,
      edges: {
        ...current.edges,
        classes: {
          ...(current.edges?.classes || {}),
          [classId]: {
            ...(current.edges?.classes?.[classId] || {}),
            ...patch
          }
        }
      }
    }));
  };

  const setEnvironment = (patch) => {
    updateThemeSettings((current) => ({
      ...current,
      environment: {
        ...current.environment,
        ...patch
      }
    }));
  };

  const setLighting = (patch) => {
    updateThemeSettings((current) => ({
      ...current,
      lighting: {
        ...current.lighting,
        ...patch
      }
    }));
  };

  const setThemeColor = (path, nextValue, mode = "") => {
    updateThemeSettings((current) => {
      const normalized = normalizeThemeSettings(current);
      const modeColors = cloneModeColors(normalized.modeColors);
      const next = {
        ...normalized,
        modeColors
      };
      if (mode === THEME_COLOR_MODES.LIGHT || mode === THEME_COLOR_MODES.DARK) {
        setPathValue(modeColors[mode], path, nextValue);
        return next;
      }
      const activeMode = activeThemeColorMode(normalized, resolvedColorSchemeMode);
      setPathValue(next, path, nextValue);
      setPathValue(modeColors[activeMode], path, nextValue);
      return next;
    });
  };
  const themeColorFieldProps = {
    themeSettings,
    resolvedColorSchemeMode,
    onChange: setThemeColor
  };

  const setLightConfig = (lightKey, patch) => {
    updateThemeSettings((current) => ({
      ...current,
      lighting: {
        ...current.lighting,
        [lightKey]: {
          ...current.lighting[lightKey],
          ...patch
        }
      }
    }));
  };

  const setLightPosition = (lightKey, axis, nextValue) => {
    updateThemeSettings((current) => ({
      ...current,
      lighting: {
        ...current.lighting,
        [lightKey]: {
          ...current.lighting[lightKey],
          position: {
            ...current.lighting[lightKey].position,
            [axis]: nextValue
          }
        }
      }
    }));
  };

  return (
    <Section
      title={appearanceTitle}
      value="appearance"
      data-cad-theme-appearance-section="true"
    >
      <ThemeAppearanceSection
        themePresets={themePresets}
        themeSettings={themeSettings}
        themePresetId={themePresetId}
        updateThemeSettings={updateThemeSettings}
        handleResetThemeSettings={handleResetThemeSettings}
        handleSaveCustomThemePreset={handleSaveCustomThemePreset}
        handleUpdateThemePresetSettings={handleUpdateThemePresetSettings}
      />

      <ControlSubsection title="Surface">
        <Field label="Colors" value={`${resolveFillColors(themeSettings.materials).length}/${MAX_THEME_FILL_COLORS}`}>
          <FillColorEditor
            colors={resolveFillColors(themeSettings.materials)}
            cycleColors={themeSettings.materials.cycleColors === true}
            onChange={(nextColors) => setMaterials({
              defaultColor: nextColors[0],
              fillColors: nextColors
            })}
          />
        </Field>

        <ThemeToggleRow
          label="Cycle colors"
          checked={themeSettings.materials.cycleColors === true}
          onChange={(nextValue) => setMaterials({ cycleColors: nextValue })}
        />

        <ThemeToggleRow
          label="Override colors"
          checked={themeSettings.materials.overrideSourceColors === true}
          onChange={(nextValue) => setMaterials({ overrideSourceColors: nextValue })}
        />

        <SliderField label="Saturation" value={formatNumber(themeSettings.materials.saturation)}>
          <SliderInput
            value={themeSettings.materials.saturation}
            min={0}
            max={2.5}
            step={0.01}
            onChange={(nextValue) => setMaterials({ saturation: nextValue })}
          />
        </SliderField>

        <SliderField label="Contrast" value={formatNumber(themeSettings.materials.contrast)}>
          <SliderInput
            value={themeSettings.materials.contrast}
            min={0}
            max={2.5}
            step={0.01}
            onChange={(nextValue) => setMaterials({ contrast: nextValue })}
          />
        </SliderField>

        <SliderField label="Brightness" value={formatNumber(themeSettings.materials.brightness)}>
          <SliderInput
            value={themeSettings.materials.brightness}
            min={0}
            max={2}
            step={0.01}
            onChange={(nextValue) => setMaterials({ brightness: nextValue })}
          />
        </SliderField>
      </ControlSubsection>

      {showEdgeSettings ? (
        <ControlSubsection title="Edges">
          <ThemeToggleRow
            label="Show edges"
            checked={themeSettings.edges.enabled}
            onChange={(nextValue) => setEdges({ enabled: nextValue })}
          />

          {showEdgeDetailControls ? (
            <>
              <ColorModeField
                label="Edge color"
                path={["edges", "color"]}
                {...themeColorFieldProps}
              />
              <div className="space-y-1">
                {EDGE_CLASS_CONTROLS.map((edgeClass) => {
                  const settings = themeSettings.edges.classes?.[edgeClass.id] || {};
                  const thickness = settings.thickness ?? edgeClass.defaultThickness;
                  const opacity = settings.opacity ?? edgeClass.defaultOpacity;
                  const available = !availableEdgeClassSet || availableEdgeClassSet.has(edgeClass.id);
                  const checked = available && thickness > 0 && opacity > 0;
                  return (
                    <EdgeClassControlRow
                      key={edgeClass.id}
                      label={edgeClass.label}
                      checked={checked}
                      available={available}
                      thickness={thickness}
                      opacity={opacity}
                      onEnabledChange={(nextValue) => setEdgeClass(edgeClass.id, nextValue
                        ? {
                            thickness: thickness > 0 ? thickness : edgeClass.defaultThickness,
                            opacity: opacity > 0 ? opacity : edgeClass.defaultOpacity
                          }
                        : { thickness: 0 })}
                      onThicknessChange={(nextValue) => setEdgeClass(edgeClass.id, { thickness: nextValue })}
                      onOpacityChange={(nextValue) => setEdgeClass(edgeClass.id, { opacity: nextValue })}
                    />
                  );
                })}
              </div>
            </>
          ) : null}
        </ControlSubsection>
      ) : null}

      {showEdgeDetailControls ? (
        <ControlSubsection title="Highlight">
          <ColorField
            label="Color"
            value={themeSettings.edges.highlightColor || "#8dc5ff"}
            onChange={(nextValue) => setEdges({ highlightColor: nextValue })}
          />
          <HighlightEdgeSlidersRow
            thickness={themeSettings.edges.highlightThickness ?? 3}
            opacity={themeSettings.edges.highlightOpacity ?? 1}
            onThicknessChange={(nextValue) => setEdges({ highlightThickness: nextValue })}
            onOpacityChange={(nextValue) => setEdges({ highlightOpacity: nextValue })}
          />
        </ControlSubsection>
      ) : null}

      <ControlSubsection title="Backdrop">
        <Field label="Style">
          <SegmentedControl
            value={themeSettings.background.type}
            onChange={(nextValue) => setBackground({ type: nextValue })}
            options={BACKGROUND_MODE_OPTIONS}
          />
        </Field>

        {themeSettings.background.type === "solid" ? (
          <ColorModeField
            label="Color"
            path={["background", "solidColor"]}
            {...themeColorFieldProps}
          />
        ) : null}

        {themeSettings.background.type === "linear" ? (
          <>
            <ColorModeField
              label="Start color"
              path={["background", "linearStart"]}
              {...themeColorFieldProps}
            />
            <ColorModeField
              label="End color"
              path={["background", "linearEnd"]}
              {...themeColorFieldProps}
            />
            <SliderField label="Angle" value={`${formatNumber(themeSettings.background.linearAngle, 0)} deg`}>
              <SliderInput
                value={themeSettings.background.linearAngle}
                min={-360}
                max={360}
                step={1}
                onChange={(nextValue) => setBackground({ linearAngle: nextValue })}
              />
            </SliderField>
          </>
        ) : null}

        {themeSettings.background.type === "radial" ? (
          <>
            <ColorModeField
              label="Inner color"
              path={["background", "radialInner"]}
              {...themeColorFieldProps}
            />
            <ColorModeField
              label="Outer color"
              path={["background", "radialOuter"]}
              {...themeColorFieldProps}
            />
          </>
        ) : null}
      </ControlSubsection>

      <ControlSubsection title="Floor">
        <Field label="Mode">
          <SegmentedControl
            value={themeSettings.floor?.mode || THEME_FLOOR_MODES.STAGE}
            onChange={(nextValue) => setFloor({ mode: nextValue })}
            options={FLOOR_MODE_OPTIONS}
          />
        </Field>
        {(themeSettings.floor?.mode || THEME_FLOOR_MODES.STAGE) === THEME_FLOOR_MODES.STAGE ? (
          <>
            <ColorModeField
              label="Color"
              path={["floor", "color"]}
              {...themeColorFieldProps}
            />
            <SliderField label="Roughness" value={formatNumber(themeSettings.floor?.roughness ?? 0.72)}>
              <SliderInput
                value={themeSettings.floor?.roughness ?? 0.72}
                min={0}
                max={1}
                step={0.01}
                onChange={(nextValue) => setFloor({ roughness: nextValue })}
              />
            </SliderField>
            <SliderField label="Reflectivity" value={formatNumber(themeSettings.floor?.reflectivity ?? 0.12)}>
              <SliderInput
                value={themeSettings.floor?.reflectivity ?? 0.12}
                min={0}
                max={1}
                step={0.01}
                onChange={(nextValue) => setFloor({ reflectivity: nextValue })}
              />
            </SliderField>
            <SliderField label="Shadow" value={formatNumber(themeSettings.floor?.shadowOpacity ?? 0.45)}>
              <SliderInput
                value={themeSettings.floor?.shadowOpacity ?? 0.45}
                min={0}
                max={1}
                step={0.01}
                onChange={(nextValue) => setFloor({ shadowOpacity: nextValue })}
              />
            </SliderField>
            <SliderField label="Backdrop blend" value={formatNumber(themeSettings.floor?.horizonBlend ?? 0)}>
              <SliderInput
                value={themeSettings.floor?.horizonBlend ?? 0}
                min={0}
                max={1}
                step={0.01}
                onChange={(nextValue) => setFloor({ horizonBlend: nextValue })}
              />
            </SliderField>
          </>
        ) : null}
        {(themeSettings.floor?.mode || THEME_FLOOR_MODES.STAGE) === THEME_FLOOR_MODES.GRID ? (
          <>
            <ColorModeField
              label="Center line"
              path={["floor", "gridCenterColor"]}
              {...themeColorFieldProps}
            />
            <ColorModeField
              label="Cell line"
              path={["floor", "gridCellColor"]}
              {...themeColorFieldProps}
            />
            <SliderField label="Line opacity" value={formatNumber(themeSettings.floor?.gridOpacity ?? 0.18)}>
              <SliderInput
                value={themeSettings.floor?.gridOpacity ?? 0.18}
                min={0}
                max={1}
                step={0.01}
                onChange={(nextValue) => setFloor({ gridOpacity: nextValue })}
              />
            </SliderField>
            <SliderField label="Density" value={formatNumber(themeSettings.floor?.gridDensity ?? 1)}>
              <SliderInput
                value={themeSettings.floor?.gridDensity ?? 1}
                min={0.25}
                max={4}
                step={0.05}
                onChange={(nextValue) => setFloor({ gridDensity: nextValue })}
              />
            </SliderField>
          </>
        ) : null}
      </ControlSubsection>

      <ControlSubsection title="Lighting">
        <ThemeToggleRow
          label="Environment light"
          checked={themeSettings.environment.enabled}
          onChange={(nextValue) => setEnvironment({ enabled: nextValue })}
        />
        <SliderField label="Environment intensity" value={formatNumber(themeSettings.environment.intensity)}>
          <SliderInput
            value={themeSettings.environment.intensity}
            min={0}
            max={4}
            step={0.01}
            onChange={(nextValue) => setEnvironment({ intensity: nextValue })}
          />
        </SliderField>

        <SliderField label="Tone mapping" value={formatNumber(themeSettings.lighting.toneMappingExposure)}>
          <SliderInput
            value={themeSettings.lighting.toneMappingExposure}
            min={0.05}
            max={6}
            step={0.01}
            onChange={(nextValue) => setLighting({ toneMappingExposure: nextValue })}
          />
        </SliderField>

        <NestedControlGroup title="Primary">
          <Tabs value={activePrimaryLight} onValueChange={setActivePrimaryLight} className="gap-0">
            <div className="px-3 py-1">
              <TabsList className="grid h-7 w-full grid-cols-3 rounded-md p-0.5">
                {PRIMARY_LIGHT_OPTIONS.map((option) => (
                  <TabsTrigger key={option.value} value={option.value} className="text-[11px]">
                    {option.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>

            {PRIMARY_LIGHT_OPTIONS.map((option) => {
              const light = themeSettings.lighting[option.value];
              const supportsDistance = option.value !== "directional";
              return (
                <TabsContent
                  key={option.value}
                  value={option.value}
                  className={cn("mt-2", FILE_SHEET_ROW_STACK_CLASSES)}
                  data-file-sheet-row-stack=""
                >
                  <ThemeToggleRow
                    label={`${option.label} light`}
                    checked={light.enabled}
                    onChange={(nextValue) => setLightConfig(option.value, { enabled: nextValue })}
                  />
                  <ColorModeField
                    label="Color"
                    path={["lighting", option.value, "color"]}
                    {...themeColorFieldProps}
                  />
                  <SliderField label="Intensity" value={formatNumber(light.intensity)}>
                    <SliderInput
                      value={light.intensity}
                      min={0}
                      max={20}
                      step={0.01}
                      onChange={(nextValue) => setLightConfig(option.value, { intensity: nextValue })}
                    />
                  </SliderField>
                  {option.value === "spot" ? (
                    <SliderField label="Angle" value={formatNumber(light.angle)}>
                      <SliderInput
                        value={light.angle}
                        min={0.01}
                        max={1.57}
                        step={0.01}
                        onChange={(nextValue) => setLightConfig(option.value, { angle: nextValue })}
                      />
                    </SliderField>
                  ) : null}
                  {supportsDistance ? (
                    <SliderField label="Distance" value={formatNumber(light.distance, 0)}>
                      <SliderInput
                        value={light.distance}
                        min={0}
                        max={5000}
                        step={1}
                        onChange={(nextValue) => setLightConfig(option.value, { distance: nextValue })}
                      />
                    </SliderField>
                  ) : null}
                  <Field label="Position (X/Z)">
                    <PositionPad
                      value={light.position}
                      onChange={(axis, nextValue) => setLightPosition(option.value, axis, nextValue)}
                    />
                  </Field>
                  <SliderField label="Height (Y)" value={formatNumber(light.position.y, 0)}>
                    <SliderInput
                      value={light.position.y}
                      min={-5000}
                      max={5000}
                      step={1}
                      onChange={(nextValue) => setLightPosition(option.value, "y", nextValue)}
                    />
                  </SliderField>
                </TabsContent>
              );
            })}
          </Tabs>
        </NestedControlGroup>

        <NestedControlGroup title="Ambient">
          <ThemeToggleRow
            label="Ambient light"
            checked={themeSettings.lighting.ambient.enabled}
            onChange={(nextValue) => setLightConfig("ambient", { enabled: nextValue })}
          />
          <ColorModeField
            label="Ambient color"
            path={["lighting", "ambient", "color"]}
            {...themeColorFieldProps}
          />
          <SliderField label="Ambient intensity" value={formatNumber(themeSettings.lighting.ambient.intensity)}>
            <SliderInput
              value={themeSettings.lighting.ambient.intensity}
              min={0}
              max={20}
              step={0.01}
              onChange={(nextValue) => setLightConfig("ambient", { intensity: nextValue })}
            />
          </SliderField>
        </NestedControlGroup>

        <NestedControlGroup title="Hemisphere">
          <ThemeToggleRow
            label="Hemisphere light"
            checked={themeSettings.lighting.hemisphere.enabled}
            onChange={(nextValue) => setLightConfig("hemisphere", { enabled: nextValue })}
          />
          <ColorModeField
            label="Sky color"
            path={["lighting", "hemisphere", "skyColor"]}
            {...themeColorFieldProps}
          />
          <ColorModeField
            label="Ground color"
            path={["lighting", "hemisphere", "groundColor"]}
            {...themeColorFieldProps}
          />
          <SliderField label="Hemisphere intensity" value={formatNumber(themeSettings.lighting.hemisphere.intensity)}>
            <SliderInput
              value={themeSettings.lighting.hemisphere.intensity}
              min={0}
              max={20}
              step={0.01}
              onChange={(nextValue) => setLightConfig("hemisphere", { intensity: nextValue })}
            />
          </SliderField>
        </NestedControlGroup>
      </ControlSubsection>
    </Section>
  );
}

export default function ThemeSettingsPopover({
  open,
  isDesktop,
  width,
  onStartResize,
  themePresets = [],
  themeSettings,
  themePresetId = "",
  resolvedColorSchemeMode = THEME_COLOR_MODES.LIGHT,
  updateThemeSettings,
  handleResetThemeSettings,
  handleSaveCustomThemePreset,
  handleUpdateThemePresetSettings,
  showEdgeSettings = true
}) {
  return (
    <FileSheet
      open={open}
      title="Theme"
      isDesktop={isDesktop}
      width={width}
      onStartResize={onStartResize}
    >
      <Accordion type="multiple" className="text-sm">
        <ThemeSettingsSections
          themePresets={themePresets}
          themeSettings={themeSettings}
          themePresetId={themePresetId}
          resolvedColorSchemeMode={resolvedColorSchemeMode}
          updateThemeSettings={updateThemeSettings}
          handleResetThemeSettings={handleResetThemeSettings}
          handleSaveCustomThemePreset={handleSaveCustomThemePreset}
          handleUpdateThemePresetSettings={handleUpdateThemePresetSettings}
          showEdgeSettings={showEdgeSettings}
          edgeAvailability={edgeAvailability}
        />
      </Accordion>
    </FileSheet>
  );
}
