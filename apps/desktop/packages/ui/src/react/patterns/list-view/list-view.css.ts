import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';

/** Root: flex column that fills available height. */
export const root = style({
  position: 'relative',
  display: 'flex',
  height: '100%',
  minHeight: 0,
  width: '100%',
  flexDirection: 'column',
});

/**
 * Toolbar: sticky header region above the list.
 * Consumers drop ToggleGroups, SearchInputs, Selects, and FilterButtons here.
 */
export const toolbar = style({
  display: 'flex',
  flexShrink: 0,
  flexDirection: 'column',
  gap: '0.5rem',
  borderBottom: `1px solid ${vars.border}`,
  paddingBottom: '0.5rem',
});

/**
 * FilterPills: row of active-filter pills below the toolbar controls.
 * Only rendered when children are present (parent handles the null guard).
 */
export const filterPills = style({
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: '0.375rem',
});

/** Body: the flex-1 region that contains the VirtualList scroll container. */
export const body = style({
  display: 'flex',
  minHeight: 0,
  flex: '1 1 0%',
  flexDirection: 'column',
});

/**
 * Footer: absolute overlay pinned to the bottom of the root.
 * Use for selection bars, pagination status, or action rows that float
 * above the list content (like the tasks SelectionBar).
 */
export const footer = style({
  position: 'absolute',
  bottom: 0,
  left: 0,
  right: 0,
  zIndex: 10,
  pointerEvents: 'none',
});
globalStyle(`${footer} > *`, { pointerEvents: 'auto' });
