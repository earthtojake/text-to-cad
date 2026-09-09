import { type ComboboxRootChangeEventDetails } from '@base-ui/react/combobox';
import { cx } from '@styles/utilities/cx';
import { ChevronDown } from 'lucide-react';
import * as React from 'react';
import { Combobox } from '@/react/primitives/combobox/combobox';
import {
  HoverCard,
  isEventInsideInteractiveLayer,
  useHoverCard,
} from '@/react/primitives/hover-card';
import * as styles from './combobox-popover.css';

export interface ComboboxPopoverProps<T> {
  items: T[];
  value: string | null | undefined;
  onValueChange: (value: string) => void;
  /** Extract a stable unique key from an item. */
  itemToKey: (item: T) => string;
  /** Extract the primary display label from an item. */
  itemToLabel: (item: T) => string;
  /**
   * Custom filter predicate. Defaults to a case-insensitive label substring
   * match so items with no matching substring are hidden.
   */
  filter?: (item: T, query: string) => boolean;
  /**
   * Render the trigger button content.
   * Receives the currently selected item (or `null` when nothing is selected).
   */
  renderTrigger: (selected: T | null) => React.ReactNode;
  /** Optional title/label for the trigger button. */
  triggerTitle?: (selected: T | null) => string | undefined;
  /** Optional id used to associate the trigger with an external form label. */
  triggerId?: string;
  /**
   * Render the content of each list row.
   * Receives the item; the row wrapper (hover/selected states) is provided by
   * the primitive.
   */
  renderItem: (item: T) => React.ReactNode;
  /**
   * When provided a detail hover card is shown beside the list on row hover.
   * Receives the currently hovered item.
   */
  renderItemDetail?: (item: T) => React.ReactNode;
  /** Placeholder text inside the search input. */
  searchPlaceholder?: string;
  disabled?: boolean;
  className?: string;
  contentClassName?: string;
  contentStyle?: React.CSSProperties;
  contentWidth?: 'trigger' | 'content' | 'content-at-least-trigger';
  onOpenChange?: (open: boolean) => void;
  /** Side for the detail hover card relative to the list popup. Defaults to 'right'. */
  detailSide?: 'top' | 'bottom' | 'left' | 'right';
  /** Align for the detail hover card. Defaults to 'start'. */
  detailAlign?: 'start' | 'center' | 'end';
  /**
   * Optional footer rendered inside the popup but OUTSIDE the filtered item
   * collection. A separator is inserted automatically above the footer.
   * Use this for action rows (e.g. "Open settings", "Manage providers") that
   * should remain visible regardless of what the user types in the search box.
   */
  renderFooter?: () => React.ReactNode;
  /**
   * Visual appearance of the trigger button.
   * - `control` (default): ghost button — matches dropdowns and toolbar triggers.
   * - `input`: matches Input/Textarea — border, surfaceInput background, focus ring.
   *   Use in form contexts via ComboboxSelectField.
   */
  appearance?: 'control' | 'input';
}

export function ComboboxPopover<T>({
  items,
  value,
  onValueChange,
  itemToKey,
  itemToLabel,
  filter,
  renderTrigger,
  triggerTitle,
  triggerId,
  renderItem,
  renderItemDetail,
  renderFooter,
  searchPlaceholder = 'Search…',
  disabled = false,
  className,
  contentClassName,
  contentStyle,
  contentWidth = 'trigger',
  onOpenChange,
  detailSide = 'right',
  detailAlign = 'start',
  appearance = 'control',
}: ComboboxPopoverProps<T>) {
  const [open, setOpen] = React.useState(false);
  const [anchorEl, setAnchorEl] = React.useState<HTMLElement | null>(null);
  const hoverCard = useHoverCard();

  const selectedItem = value != null ? (items.find((i) => itemToKey(i) === value) ?? null) : null;
  const triggerTitleValue = triggerTitle?.(selectedItem);

  const activeDetailItem =
    renderItemDetail && hoverCard.activeKey != null
      ? (items.find((i) => itemToKey(i) === hoverCard.activeKey) ?? null)
      : null;

  const defaultFilter = React.useCallback(
    (item: T, query: string) => itemToLabel(item).toLowerCase().includes(query.toLowerCase()),
    [itemToLabel]
  );

  function updateOpen(next: boolean) {
    setOpen(next);
    onOpenChange?.(next);
  }

  function handleOpenChange(next: boolean, eventDetails: ComboboxRootChangeEventDetails) {
    if (disabled) return;
    // Interactions inside the hover card OR inside any other nested interactive
    // layer (e.g. a footer submenu rendered in its own portal) must not close
    // the combobox list — cancel the dismissal.
    // isEventInsideInteractiveLayer already recognises [data-slot="dropdown-menu-content"]
    // so effort-submenu interactions are caught here.
    if (!next && isEventInsideInteractiveLayer(eventDetails.event, anchorEl)) {
      eventDetails.cancel();
      return;
    }
    if (!next) hoverCard.close();
    updateOpen(next);
  }

  function handleValueChange(item: T | null) {
    if (!item || disabled) return;
    hoverCard.close();
    onValueChange(itemToKey(item));
    updateOpen(false);
  }

  return (
    <Combobox.Root
      items={items}
      value={selectedItem ?? null}
      onValueChange={handleValueChange}
      open={open}
      onOpenChange={disabled ? undefined : handleOpenChange}
      isItemEqualToValue={(a: T, b: T) => itemToKey(a) === itemToKey(b)}
      filter={filter ?? defaultFilter}
      autoHighlight
    >
      <Combobox.Trigger
        id={triggerId}
        disabled={disabled}
        title={triggerTitleValue}
        aria-label={triggerTitleValue}
        className={
          appearance === 'input'
            ? cx(...styles.triggerInput, className)
            : cx(styles.trigger, className)
        }
      >
        <span className={styles.triggerLabel}>{renderTrigger(selectedItem)}</span>
        <ChevronDown className={styles.triggerChevron} />
      </Combobox.Trigger>

      <Combobox.Content
        ref={setAnchorEl}
        width={contentWidth}
        className={cx(styles.contentMinWidth, contentClassName)}
        style={contentStyle}
      >
        <Combobox.Input showTrigger={false} placeholder={searchPlaceholder} />
        <Combobox.List>
          {(item: T) => {
            const key = itemToKey(item);
            return (
              <Combobox.Item
                key={key}
                value={item}
                {...(renderItemDetail ? hoverCard.getRowHoverProps(key) : {})}
              >
                {renderItem(item)}
              </Combobox.Item>
            );
          }}
        </Combobox.List>
        {renderFooter && (
          <>
            <Combobox.Separator />
            {renderFooter()}
          </>
        )}
      </Combobox.Content>

      {renderItemDetail && activeDetailItem && (
        <HoverCard
          anchor={anchorEl}
          ownPopup={anchorEl ?? undefined}
          controller={hoverCard}
          side={detailSide}
          align={detailAlign}
        >
          {renderItemDetail(activeDetailItem)}
        </HoverCard>
      )}
    </Combobox.Root>
  );
}
