import { cn } from '@cad/ui/utils';

/**
 * Figma's one rule for a control: its LABEL is muted (`--muted-foreground`), its VALUE — the number, the
 * option chosen, a field's text — is the foreground. Every labelled control (a slider, a select row, a
 * toggle, a number field, a menu's setting row, a card's fact) names itself with `FieldLabel`, so no
 * control sets a label colour, weight or size of its own: the label takes the size of where it stands
 * (the panel's 12px, a menu's), at normal weight. `FIELD_VALUE_CLASS` is the value's colour, for a
 * value that is not a control drawing its own (an input's text already is the foreground).
 */
export const FIELD_LABEL_CLASS = 'min-w-0 truncate font-normal text-muted-foreground';
export const FIELD_VALUE_CLASS = 'text-foreground';

/** A control's label. `as`: its element (a `dt` in a card's facts). */
export function FieldLabel({ as: Component = 'span', className, ...props }) {
  return <Component data-field-label='' className={cn('block', FIELD_LABEL_CLASS, className)} {...props} />;
}
