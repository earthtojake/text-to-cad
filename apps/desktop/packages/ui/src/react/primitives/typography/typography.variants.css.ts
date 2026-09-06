/**
 * textVariants — Vanilla Extract recipe replacing the CVA textVariants.
 * Each variant applies the role's type tokens directly via the --type-* CSS vars
 * from theme.base.css, replacing the text-role-* class indirection.
 */

import { nsVar } from '@emdash/theme';
import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { vars } from '@theme/core/contract/contract.css';

export const textVariants = recipe({
  base: {},

  variants: {
    variant: {
      body: {
        fontFamily: nsVar('type-body-font-family'),
        fontSize: nsVar('type-body-font-size'),
        fontWeight: nsVar('type-body-font-weight'),
        lineHeight: nsVar('type-body-line-height'),
      },
      bodyItalic: {
        fontFamily: nsVar('type-body-italic-font-family'),
        fontSize: nsVar('type-body-italic-font-size'),
        fontWeight: nsVar('type-body-italic-font-weight'),
        fontStyle: 'italic',
        lineHeight: nsVar('type-body-italic-line-height'),
      },
      bodyLink: {
        fontFamily: nsVar('type-body-link-font-family'),
        fontSize: nsVar('type-body-link-font-size'),
        fontWeight: nsVar('type-body-link-font-weight'),
        lineHeight: nsVar('type-body-link-line-height'),
      },
      h1: {
        fontFamily: nsVar('type-h1-font-family'),
        fontSize: nsVar('type-h1-font-size'),
        fontWeight: nsVar('type-h1-font-weight'),
        lineHeight: nsVar('type-h1-line-height'),
      },
      h2: {
        fontFamily: nsVar('type-h2-font-family'),
        fontSize: nsVar('type-h2-font-size'),
        fontWeight: nsVar('type-h2-font-weight'),
        lineHeight: nsVar('type-h2-line-height'),
      },
      h3: {
        fontFamily: nsVar('type-h3-font-family'),
        fontSize: nsVar('type-h3-font-size'),
        fontWeight: nsVar('type-h3-font-weight'),
        lineHeight: nsVar('type-h3-line-height'),
      },
      section: {
        fontFamily: nsVar('type-section-font-family'),
        fontSize: nsVar('type-section-font-size'),
        fontWeight: nsVar('type-section-font-weight'),
        lineHeight: nsVar('type-section-line-height'),
      },
      caption: {
        fontFamily: nsVar('type-caption-font-family'),
        fontSize: nsVar('type-caption-font-size'),
        fontWeight: nsVar('type-caption-font-weight'),
        lineHeight: nsVar('type-caption-line-height'),
      },
      description: {
        fontFamily: nsVar('type-description-font-family'),
        fontSize: nsVar('type-description-font-size'),
        fontWeight: nsVar('type-description-font-weight'),
        lineHeight: nsVar('type-description-line-height'),
      },
      inlineCode: {
        fontFamily: nsVar('type-inline-code-font-family'),
        fontSize: nsVar('type-inline-code-font-size'),
        fontWeight: nsVar('type-inline-code-font-weight'),
        lineHeight: nsVar('type-inline-code-line-height'),
      },
      code: {
        fontFamily: nsVar('type-code-font-family'),
        fontSize: nsVar('type-code-font-size'),
        fontWeight: nsVar('type-code-font-weight'),
        lineHeight: nsVar('type-code-line-height'),
      },
      codeLang: {
        fontFamily: nsVar('type-code-lang-font-family'),
        fontSize: nsVar('type-code-lang-font-size'),
        fontWeight: nsVar('type-code-lang-font-weight'),
        lineHeight: nsVar('type-code-lang-line-height'),
      },
      mention: {
        fontFamily: nsVar('type-mention-font-family'),
        fontSize: nsVar('type-mention-font-size'),
        fontWeight: nsVar('type-mention-font-weight'),
        lineHeight: nsVar('type-mention-line-height'),
      },
    },
    tone: {
      default: { color: vars.foreground },
      muted: { color: vars.foregroundMuted },
      passive: { color: vars.foregroundPassive },
      inherit: {},
    },
  },

  defaultVariants: {
    variant: 'body',
    tone: 'inherit',
  },
});

export type TextVariantProps = NonNullable<RecipeVariants<typeof textVariants>>;
