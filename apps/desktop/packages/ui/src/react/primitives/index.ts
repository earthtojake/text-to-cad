// ── Single-component primitives (named exports) ───────────────────────────────
export { AnimatedHeight, type AnimatedHeightProps } from './animated-height';
export { Box } from './box';
export { Badge, type BadgeProps, type BadgeTone, type BadgeVariant } from './badge';
export { Breadcrumbs, type BreadcrumbItem, type BreadcrumbsProps } from './breadcrumbs';
export { Button, type ButtonProps } from './button';
export { Checkbox, type CheckboxProps } from './checkbox';
export { DirectoryField, type DirectoryFieldProps } from './directory-field';
export { Icon, type IconName, type IconProps, type IconSize } from './icon';
export { Input, type InputProps } from './input';
export { Kbd, KbdGroup, type KbdGroupProps, type KbdProps } from './kbd';
export { Label, MicroLabel, type LabelProps } from './label';
export { Separator, type SeparatorProps } from './separator';
export { Spinner, type SpinnerProps, type SpinnerSize } from './spinner';
export { ModalLayout, type ModalLayoutProps } from './modal-layout';
export { ShowHide, type ShowHideProps } from './show-hide';
export { Textarea, type TextareaProps } from './textarea';
export { Switch, type SwitchProps } from './switch';
export { SearchInput, type SearchInputProps } from './search-input';
export { ScrollContainer, type ScrollContainerProps } from './scroll-container';
export { SeparatedList, type SeparatedListProps } from './separated-list';
export { SelectableCard, type SelectableCardProps } from './selectable-card';
export { Surface, useSurfaceLevel, type SurfaceProps } from './surface/surface';
export { TriggerButton, type TriggerButtonProps } from './trigger-button';
export { Text, type TextProps } from './typography/Text';
export { AbsoluteTime, type AbsoluteTimeProps } from './time/absolute-time';
export { RelativeTime, type RelativeTimeProps } from './time/relative-time';
export { Heading, type HeadingProps } from './typography/Heading';
export { textVariants, type TextVariantProps } from './typography/typography.variants';

// ── Toggle (standalone) + ToggleGroup namespace ───────────────────────────────
export { Toggle, ToggleGroup, type ToggleProps, type ToggleGroupProps } from './toggle';

// ── Multi-part namespace consts ───────────────────────────────────────────────
export { Select } from './select';
export { RadioGroup } from './radio-group';
export { Dialog, type DialogSize } from './dialog';
export { Sheet, type SheetSide } from './sheet';
export { Popover } from './popover';
export { Tooltip } from './tooltip';
export { DropdownMenu } from './dropdown-menu';
export { ContextMenu } from './context-menu';
export { Combobox, useComboboxAnchor } from './combobox/combobox';
export { Tabs, type TabsTabProps } from './tabs/tabs';
export { Collapsible, type CollapsibleTriggerProps } from './collapsible';
export { InputGroup, type InputGroupAddonAlign } from './input-group';
export { Alert, type AlertProps } from './alert';
export { Field, type FieldLegendVariants, type FieldVariants } from './field';
export {
  Resizable,
  useCollapsiblePanelBinding,
  useResizableDefaultLayout,
  type CollapsiblePanelBinding,
  type CollapsiblePanelBindingOptions,
  type LayoutStorage,
  type ResizableGroupProps,
  type ResizableHandleProps,
  type ResizablePanelProps,
} from './resizable';

// ── Non-namespaced compound helpers (remain as named exports) ─────────────────
export {
  ComboboxPopup,
  ComboboxPopupDismiss,
  type ComboboxPopupItem,
  type ComboboxPopupHandle,
} from './combobox/combobox-popup';
export {
  useHoverCard,
  HoverCard,
  isEventInsideInteractiveLayer,
  type HoverCardController,
  type HoverCardRowProps,
  type HoverCardProps,
} from './hover-card';
export {
  SplitButton,
  type SplitButtonProps,
  type SplitButtonOption,
  type SplitButtonOptionTone,
} from './split-button';

export { SegmentedSpinnerIcon, type SegmentedSpinnerIconProps } from './segmented-spinner';
export {
  useAsyncAction,
  type AsyncActionTrigger,
  type UseAsyncActionOptions,
} from './hooks/use-async-action';

// ── Toast (imperative namespace + hook + app-mounted Toaster) ────────────────
export {
  Toaster,
  toast,
  useToast,
  type ToastAction,
  type ToastId,
  type ToastOptions,
  type ToastPromiseMessages,
  type ToastTone,
  type ToasterProps,
} from './toast';

// ── Theme / provider ──────────────────────────────────────────────────────────
export {
  ThemeProvider,
  useTheme,
  usePortalThemeClass,
  THEME_MANIFEST,
  type ThemeId,
  type ThemeProviderProps,
} from './theme-provider';

// ── Utility / recipe re-exports ───────────────────────────────────────────────
export { resolveFileIconClass } from '../lib/file-icons';
// Relative re-exports: the dts emitter rewrites aliased (`@styles/*`) imports
// to a dangling relative path, silently degrading the exported types.
export { controlVariants, type ControlVariantProps } from '../../styles/recipes/control';
export { inputVariants, type InputVariantProps } from '../../styles/recipes/input';
