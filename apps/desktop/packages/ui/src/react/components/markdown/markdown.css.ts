import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

// Element styles for the two Markdown variants, ported from the legacy
// Tailwind component maps onto @emdash/ui tokens. The full variant reads like
// a document; the compact variant is denser for previews and comment bodies.

const mutedTint = (percent: number) =>
  `color-mix(in srgb, ${vars.background2} ${percent}%, transparent)`;

// ── Shared ────────────────────────────────────────────────────────────────────

export const link = style({
  color: vars.foregroundInfo,
  textDecoration: 'underline',
  textDecorationColor: `color-mix(in srgb, ${vars.foregroundInfo} 50%, transparent)`,
  ':hover': {
    textDecorationColor: vars.foregroundInfo,
  },
});

export const strong = style({
  fontWeight: 600,
  color: vars.foreground,
});

export const taskCheckbox = style({
  marginRight: '0.5rem',
  verticalAlign: 'middle',
  pointerEvents: 'none',
  selectors: {
    // readOnly instead of disabled so the checked state keeps full contrast.
    '&:checked': { accentColor: vars.foregroundInfo },
  },
});

export const listItem = style({
  lineHeight: 1.625,
  selectors: {
    '& + &': { marginTop: '0.25rem' },
  },
});

// ── Full variant ──────────────────────────────────────────────────────────────

const headingBase = {
  fontWeight: 600,
  color: vars.foreground,
} as const;

export const h1Full = style({
  ...headingBase,
  marginTop: '1.5rem',
  marginBottom: '1rem',
  borderBottom: `1px solid ${vars.border}`,
  paddingBottom: '0.5rem',
  fontSize: '1.5rem',
  lineHeight: 1.33,
  selectors: { '&:first-child': { marginTop: 0 } },
});

export const h2Full = style({
  ...headingBase,
  marginTop: '1.5rem',
  marginBottom: '0.75rem',
  borderBottom: `1px solid ${vars.border}`,
  paddingBottom: '0.5rem',
  fontSize: '1.25rem',
  lineHeight: 1.4,
  selectors: { '&:first-child': { marginTop: 0 } },
});

export const h3Full = style({
  ...headingBase,
  marginTop: '1rem',
  marginBottom: '0.5rem',
  fontSize: '1.125rem',
  lineHeight: 1.55,
});

export const h4Full = style({
  ...headingBase,
  marginTop: '1rem',
  marginBottom: '0.5rem',
  fontSize: '1rem',
  lineHeight: 1.5,
});

export const h5Full = style({
  ...headingBase,
  marginTop: '0.75rem',
  marginBottom: '0.25rem',
  fontSize: tokenVars.textSm,
});

export const h6Full = style({
  ...headingBase,
  marginTop: '0.75rem',
  marginBottom: '0.25rem',
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
});

export const paragraphFull = style({
  marginBottom: '0.75rem',
  fontSize: tokenVars.textSm,
  lineHeight: 1.625,
  color: vars.foreground,
});

export const unorderedListFull = style({
  marginBottom: '0.75rem',
  marginLeft: '1.5rem',
  listStyleType: 'disc',
  fontSize: tokenVars.textSm,
  color: vars.foreground,
});

export const orderedListFull = style({
  marginBottom: '0.75rem',
  marginLeft: '1.5rem',
  listStyleType: 'decimal',
  fontSize: tokenVars.textSm,
  color: vars.foreground,
});

export const inlineCodeFull = style({
  backgroundColor: vars.background2,
  borderRadius: tokenVars.radiusSm,
  paddingInline: '0.375rem',
  paddingBlock: '0.125rem',
  fontFamily: tokenVars.fontMono,
  fontSize: tokenVars.textXs,
});

export const preFull = style({
  marginBottom: '0.75rem',
  overflowX: 'auto',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid ${vars.border}`,
  backgroundColor: vars.background1,
});

export const codeBlockFull = style({
  display: 'block',
  padding: '0.75rem',
  fontFamily: tokenVars.fontMono,
  fontSize: tokenVars.textXs,
  lineHeight: 1.625,
});

export const blockquoteFull = style({
  marginBottom: '0.75rem',
  borderLeft: `4px solid ${vars.border}`,
  backgroundColor: mutedTint(30),
  paddingBlock: '0.25rem',
  paddingLeft: '1rem',
  fontSize: tokenVars.textSm,
  fontStyle: 'italic',
  color: vars.foregroundMuted,
});

export const tableWrapperFull = style({
  marginBottom: '0.75rem',
  overflowX: 'auto',
});

export const tableFull = style({
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: tokenVars.textSm,
});

export const tableHeadFull = style({
  backgroundColor: mutedTint(30),
  borderBottom: `1px solid ${vars.border}`,
});

export const tableHeaderCellFull = style({
  paddingInline: '0.75rem',
  paddingBlock: '0.5rem',
  textAlign: 'left',
  fontWeight: 600,
  color: vars.foreground,
});

export const tableCellFull = style({
  borderTop: `1px solid ${vars.border}`,
  paddingInline: '0.75rem',
  paddingBlock: '0.5rem',
  color: vars.foreground,
});

export const dividerFull = style({
  marginBlock: '1.5rem',
  border: 'none',
  borderTop: `1px solid ${vars.border}`,
});

export const imageContainerFull = style({
  marginBlock: '0.75rem',
});

export const imageFull = style({
  maxWidth: '100%',
  borderRadius: tokenVars.radiusSm,
});

export const imagePlaceholder = style({
  display: 'inline-block',
  marginBlock: '0.75rem',
  fontSize: tokenVars.textXs,
  color: vars.foregroundMuted,
});

// ── Compact variant ───────────────────────────────────────────────────────────

export const h1Compact = style({
  ...headingBase,
  marginTop: '0.75rem',
  marginBottom: '0.25rem',
  fontSize: tokenVars.textSm,
  selectors: { '&:first-child': { marginTop: 0 } },
});

export const h3Compact = style({
  ...headingBase,
  marginTop: '0.5rem',
  marginBottom: '0.25rem',
  fontSize: tokenVars.textXs,
});

export const paragraphCompact = style({
  marginBottom: '0.5rem',
  lineHeight: 1.625,
});

export const unorderedListCompact = style({
  marginBottom: '0.5rem',
  marginLeft: '1rem',
  listStyleType: 'disc',
});

export const orderedListCompact = style({
  marginBottom: '0.5rem',
  marginLeft: '1rem',
  listStyleType: 'decimal',
});

// List markers live on the li children; both elements are owned by this
// component, so the descendant globalStyle stays within its boundary.
globalStyle(`${unorderedListCompact} > li::marker, ${orderedListCompact} > li::marker`, {
  color: vars.foregroundMuted,
});

export const inlineCodeCompact = style({
  backgroundColor: mutedTint(60),
  borderRadius: tokenVars.radiusSm,
  paddingInline: '0.25rem',
  paddingBlock: '0.125rem',
  fontFamily: tokenVars.fontMono,
  fontSize: '0.92em',
});

export const codeBlockCompact = style({
  display: 'block',
  overflowX: 'auto',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid ${vars.border}`,
  backgroundColor: mutedTint(60),
  padding: '0.5rem',
  fontFamily: tokenVars.fontMono,
  fontSize: '11px',
  lineHeight: 1.625,
});

export const preCompact = style({
  marginBottom: '0.5rem',
  overflowX: 'auto',
});

export const blockquoteCompact = style({
  marginBottom: '0.5rem',
  borderLeft: `2px solid ${vars.border}`,
  paddingLeft: '0.75rem',
  fontStyle: 'italic',
  color: vars.foregroundMuted,
});

export const tableWrapperCompact = style({
  marginBlock: '0.75rem',
  overflowX: 'auto',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid ${vars.border}`,
});

export const tableCompact = style({
  width: '100%',
  minWidth: 'max-content',
  borderCollapse: 'collapse',
  textAlign: 'left',
  fontSize: '11px',
  lineHeight: 1.375,
});

export const tableHeadCompact = style({
  backgroundColor: mutedTint(50),
  borderBottom: `1px solid ${vars.border}`,
  color: vars.foreground,
});

export const tableHeaderCellCompact = style({
  borderRight: `1px solid ${vars.border}`,
  paddingInline: '0.625rem',
  paddingBlock: '0.375rem',
  fontWeight: 600,
  selectors: { '&:last-child': { borderRight: 'none' } },
});

export const tableCellCompact = style({
  borderTop: `1px solid ${vars.border}`,
  borderRight: `1px solid ${vars.border}`,
  paddingInline: '0.625rem',
  paddingBlock: '0.375rem',
  verticalAlign: 'top',
  selectors: { '&:last-child': { borderRight: 'none' } },
});

export const dividerCompact = style({
  marginBlock: '1rem',
  border: 'none',
  borderTop: `1px solid ${vars.border}`,
});

export const linkCompact = style({
  color: vars.foregroundInfo,
  textDecoration: 'underline',
});

export const imageContainerCompact = style({
  marginBlock: '0.5rem',
});

export const imageCompact = style({
  height: 'auto',
  maxHeight: '20rem',
  maxWidth: '100%',
  borderRadius: tokenVars.radiusSm,
});

// ── Mermaid ───────────────────────────────────────────────────────────────────

export const mermaidPreviewContainer = style({
  position: 'relative',
  overflowX: 'auto',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid ${vars.border}`,
  backgroundColor: vars.background,
});

export const mermaidExpandButton = style({
  position: 'absolute',
  top: '0.25rem',
  right: '0.25rem',
  zIndex: 10,
  opacity: 0,
  transition: 'opacity 150ms',
  backgroundColor: vars.surface,
  boxShadow: `${vars.shadowSm}, 0 0 0 1px color-mix(in srgb, ${vars.border} 80%, transparent)`,
  selectors: {
    [`${mermaidPreviewContainer}:hover &`]: { opacity: 1 },
    '&:focus-visible': { opacity: 1 },
  },
});

export const mermaidPreview = style({
  minWidth: 'fit-content',
  cursor: 'zoom-in',
  padding: '0.5rem',
  color: vars.foreground,
});

export const mermaidPreviewCompact = style({
  padding: '0.375rem',
});

export const mermaidDialogContent = style({
  color: vars.foreground,
});

// The SVG markup is injected by this component via dangerouslySetInnerHTML,
// so these descendant rules do not cross a component boundary.
globalStyle(`${mermaidPreview} svg`, { display: 'block', height: 'auto', maxWidth: '100%' });
globalStyle(`${mermaidDialogContent} svg`, { display: 'block', height: 'auto', maxWidth: 'none' });

export const mermaidError = style({
  marginBlock: '0.75rem',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid color-mix(in srgb, ${vars.borderDestructive} 30%, transparent)`,
  backgroundColor: `color-mix(in srgb, ${vars.backgroundDestructive} 40%, transparent)`,
  padding: '0.75rem',
  fontSize: tokenVars.textXs,
  color: vars.foregroundDestructive,
});

export const mermaidErrorCompact = style({
  marginBlock: '0.5rem',
  padding: '0.5rem',
  fontSize: '11px',
});

export const mermaidErrorTitle = style({
  fontWeight: 500,
});

export const mermaidErrorMessage = style({
  marginTop: '0.25rem',
  color: vars.foregroundMuted,
});

export const mermaidErrorSource = style({
  marginTop: '0.5rem',
  overflowX: 'auto',
  borderRadius: tokenVars.radiusSm,
  backgroundColor: mutedTint(60),
  padding: '0.5rem',
  fontFamily: tokenVars.fontMono,
  color: vars.foregroundMuted,
});
