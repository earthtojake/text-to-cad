import { Fragment } from 'react';
import { MousePointer2 } from 'lucide-react';
import {
  DropdownMenuCheckboxItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator
} from '@hardcore/ui/primitives/dropdown-menu';
import { CONNECTED_SELECTION, SELECT_MODES, connectedSelectionApplies } from '../../workbench/selectionFilter.js';
import ToolPopover from "../../../kit/tools/ToolPopover.jsx";

/** A tool's filter menu, opened from the tool's own button (`trigger`, the toolbar's): Measure's snapping. */
export default function SelectionFilterMenu({ value, onChange, trigger, options, menuLabel }) {
  return <ToolPopover trigger={trigger} label={menuLabel} className="w-60">
      <DropdownMenuLabel>{menuLabel}</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
        {options.map(item => <Fragment key={item.id}>
          <DropdownMenuRadioItem value={item.id}>
          <span><span className="block">{item.label}</span>{item.detail && <span className="block text-micro text-muted-foreground">{item.detail}</span>}</span>
        </DropdownMenuRadioItem></Fragment>)}
      </DropdownMenuRadioGroup>
  </ToolPopover>;
}

// The Select modes' marks, drawn for the strip's 12px icon cell in its 2-unit stroke. One cube
// throughout: whole and bold for Parts; faint, with the element a pick takes drawn solid, for
// Faces (its top face filled) and Edges (its front edge heavy). All keeps the plain pointer.
const CUBE = 'M12 2.5 20.5 7.25v9.5L12 21.5l-8.5-4.75v-9.5Z';
const CUBE_SEAMS = 'M3.5 7.25 12 12l8.5-4.75M12 12v9.5';
const faintCube = <g strokeWidth="1.5" strokeOpacity="0.45"><path d={CUBE} /><path d={CUBE_SEAMS} /></g>;
const SELECT_MODE_ICONS = {
  parts: props => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d={CUBE} /><path d={CUBE_SEAMS} />
  </svg>,
  faces: props => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" {...props}>
    {faintCube}<path d="M12 2.5 20.5 7.25 12 12 3.5 7.25Z" fill="currentColor" strokeWidth="2" />
  </svg>,
  edges: props => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" {...props}>
    {faintCube}<path d="M12 12v9.5" strokeWidth="3.5" />
  </svg>,
};

/** The Select tool's icon for `mode`: what the strip's button shows, and each mode's row in its menu. */
export function SelectModeIcon({ mode, ...props }) {
  const Icon = SELECT_MODE_ICONS[mode];
  return Icon ? <Icon data-select-mode={mode} {...props} /> : <MousePointer2 data-select-mode="all" strokeWidth={2} {...props} />;
}

/**
 * The Select tool's corner menu: the four exclusive modes, each with its icon, then the two
 * connected-selection options as checkboxes. The options are independent of the mode and of
 * each other; one that has no effect under the mode in hand stays in the menu, disabled, with
 * its choice kept. Choosing a mode closes the menu; ticking an option leaves it open.
 *
 * @param {{ trigger: import("react").ReactElement, mode: string, onModeChange(mode: string): void,
 *   assembly: boolean, connected: { edgeChain: boolean, tangentFaces: boolean },
 *   onConnectedChange(id: "edgeChain" | "tangentFaces", checked: boolean): void }} props
 *   `assembly`: Parts is offered only in an assembly.
 */
export function SelectModeMenu({ trigger, mode, onModeChange, assembly, connected, onConnectedChange }) {
  return <ToolPopover trigger={trigger} label="Select mode" className="w-44">
    <DropdownMenuRadioGroup value={mode} onValueChange={onModeChange}>
      {SELECT_MODES.filter(item => assembly || !item.assemblyOnly).map(item => <DropdownMenuRadioItem key={item.id} value={item.id}>
        <SelectModeIcon mode={item.id} className="size-3.5 text-muted-foreground" aria-hidden="true" />{item.label}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    <DropdownMenuSeparator />
    {CONNECTED_SELECTION.map(option => <DropdownMenuCheckboxItem key={option.id} checked={connected[option.id] === true}
      disabled={!connectedSelectionApplies(option.id, mode)} onSelect={event => event.preventDefault()}
      onCheckedChange={checked => onConnectedChange(option.id, checked === true)}>{option.label}</DropdownMenuCheckboxItem>)}
  </ToolPopover>;
}
