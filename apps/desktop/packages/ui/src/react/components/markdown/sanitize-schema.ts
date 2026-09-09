import { defaultSchema } from 'rehype-sanitize';

/**
 * Sanitize runs before rehype-katex so user input is sanitized but KaTeX's
 * (trusted) output passes through untouched. The schema preserves the
 * math-inline/math-display classes that remark-math emits so rehype-katex can
 * still recognize them post-sanitize, and allows `data:` image sources so
 * resolved local images survive.
 */
export const sanitizeSchema = {
  ...defaultSchema,
  protocols: {
    ...defaultSchema.protocols,
    src: [...(defaultSchema.protocols?.src || []), 'data'],
  },
  attributes: {
    ...defaultSchema.attributes,
    span: [
      ...(defaultSchema.attributes?.span || []),
      ['className', 'math', 'math-inline', 'math-display'],
    ],
    div: [
      ...(defaultSchema.attributes?.div || []),
      ['className', 'math', 'math-inline', 'math-display'],
    ],
  },
} as typeof defaultSchema;
