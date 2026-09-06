/**
 * Semantic class names assigned by the TipTap mention and slash-command
 * extensions. These classes need to exist in style.css so that the serialized
 * HTML from ProseMirror (used in clipboard/copy scenarios) can be styled
 * correctly as serialized HTML from ProseMirror.
 */
import { globalStyle } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

// Applied to mention chip DOM elements in the serialized HTML representation.
globalStyle('.mention-chip', {
  display: 'inline',
  fontSize: '0.75rem',
  fontWeight: 400,
  borderRadius: tokenVars.radiusSm,
  paddingLeft: '0.25rem',
  paddingRight: '0.25rem',
  paddingTop: '0.125rem',
  paddingBottom: '0.125rem',
  backgroundColor: vars.surfaceHover,
  color: vars.foreground,
  boxShadow: '0 0 0 1px rgba(0,0,0,0.1)',
  verticalAlign: 'baseline',
});

// Applied to slash-command chip DOM elements in the serialized HTML representation.
globalStyle('.slash-command-chip', {
  display: 'inline',
  fontSize: '0.75rem',
  fontWeight: 400,
  borderRadius: tokenVars.radiusSm,
  paddingLeft: '0.25rem',
  paddingRight: '0.25rem',
  paddingTop: '0.125rem',
  paddingBottom: '0.125rem',
  backgroundColor: vars.surfaceHover,
  color: vars.foreground,
  boxShadow: '0 0 0 1px rgba(0,0,0,0.1)',
  verticalAlign: 'baseline',
});
