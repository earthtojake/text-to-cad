/**
 * Reusable helper classes for SVG icon sizing and pointer-events.
 *
 * VE `selectors` does not allow descendant selectors like `& svg`.
 * Use globalStyle with these helper class references instead.
 */
import { globalStyle, style } from '@vanilla-extract/css';

/** Apply to any element whose child SVGs should have pointer-events:none and flex-shrink:0. */
export const svgContainer = style({});
globalStyle(`${svgContainer} svg`, { pointerEvents: 'none', flexShrink: 0 });

/** Apply to elements whose un-sized child SVGs should be 1rem × 1rem. */
export const svgDefaultSize = style({});
globalStyle(`${svgDefaultSize} svg:not([class*='size-'])`, { width: '1rem', height: '1rem' });

/** Apply to elements whose un-sized child SVGs should be 0.75rem × 0.75rem (sm controls). */
export const svgSmSize = style({});
globalStyle(`${svgSmSize} svg:not([class*='size-'])`, { width: '0.75rem', height: '0.75rem' });

/** Apply to elements whose un-sized child SVGs should be 1rem × 1rem (same as default). */
export const svgTextSize = style({});
globalStyle(`${svgTextSize} svg:not([class*='size-'])`, { width: '1rem', height: '1rem' });
