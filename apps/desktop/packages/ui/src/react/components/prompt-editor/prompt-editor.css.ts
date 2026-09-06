import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';
// Colocated chip-class styles — global selectors for TipTap-serialized HTML.
import './chip-classes.css';

export const editorWrapper = style({
  position: 'relative',
  width: '100%',
});

export const editorContent = style({
  width: '100%',
  outline: 'none',
});

export const editorPlaceholder = style({
  pointerEvents: 'none',
  position: 'absolute',
  top: 0,
  left: 0,
  fontSize: tokenVars.textBase,
  lineHeight: 1.4,
  userSelect: 'none',
  color: vars.foregroundPassive,
});

// These classes are assigned via TipTap editorProps.attributes.class
export const promptEditorContentClass = style({
  outline: 'none',
  fontSize: tokenVars.textBase,
  lineHeight: 1.4,
  color: vars.foreground,
  minHeight: '1.25rem',
});
