/**
 * Syntax token template: maps each abstract SyntaxRole to TextMate grammar
 * scope selectors used by Shiki / VSCode themes.
 *
 * Scope ordering follows the gh-dark / gh-light theme tokenColors conventions
 * so generated themes produce visually coherent results out of the box.
 *
 * Each role also carries a default palette assignment expressed as scale.step,
 * calibrated to reproduce github-light and github-dark from our palette.
 * The generator can override individual assignments per theme.
 */

import type { SyntaxRole } from './roles';

export type SyntaxScopeEntry = {
  scopes: string[];
  /** Default palette ref for light polarity e.g. "success.11" */
  lightDefault: string;
  /** Default palette ref for dark polarity */
  darkDefault: string;
};

/**
 * Full scope-to-role map.  Shiki resolves scopes coarse-to-fine so broad
 * prefixes (e.g. "keyword") catch all sub-scopes unless overridden.
 */
export const SYNTAX_TEMPLATE: Record<SyntaxRole, SyntaxScopeEntry> = {
  comment: {
    scopes: ['comment', 'punctuation.definition.comment', 'string.comment'],
    lightDefault: 'neutral.9',
    darkDefault: 'neutral.9',
  },
  keyword: {
    scopes: [
      'keyword',
      'storage.type',
      'storage.modifier',
      'keyword.control',
      'keyword.operator.new',
      'keyword.other.using',
      'keyword.other.import',
      'keyword.other.package',
    ],
    lightDefault: 'red.11',
    darkDefault: 'red.11',
  },
  string: {
    scopes: [
      'string',
      'string.quoted',
      'string.template',
      'string.interpolated',
      'punctuation.definition.string',
    ],
    lightDefault: 'blue.11',
    darkDefault: 'blue.11',
  },
  number: {
    scopes: ['constant.numeric', 'constant.language', 'constant.character', 'constant.other'],
    lightDefault: 'blue.11',
    darkDefault: 'blue.11',
  },
  function: {
    scopes: ['entity.name.function', 'support.function', 'meta.function-call', 'variable.function'],
    lightDefault: 'accent.11',
    darkDefault: 'accent.11',
  },
  type: {
    scopes: [
      'entity.name.type',
      'entity.name.class',
      'entity.name.namespace',
      'entity.name.enum',
      'entity.name.interface',
      'support.class',
      'support.type',
    ],
    lightDefault: 'amber.11',
    darkDefault: 'amber.11',
  },
  variable: {
    scopes: ['variable', 'variable.other', 'variable.parameter', 'meta.definition.variable'],
    lightDefault: 'neutral.12',
    darkDefault: 'neutral.12',
  },
  property: {
    scopes: [
      'variable.other.property',
      'variable.other.object.property',
      'support.variable.property',
      'meta.object-literal.key',
    ],
    lightDefault: 'neutral.11',
    darkDefault: 'neutral.11',
  },
  operator: {
    scopes: [
      'keyword.operator',
      'punctuation.accessor',
      'punctuation.separator',
      'meta.brace',
      'punctuation',
    ],
    lightDefault: 'neutral.10',
    darkDefault: 'neutral.10',
  },
  tag: {
    scopes: ['entity.name.tag', 'meta.tag', 'punctuation.definition.tag'],
    lightDefault: 'green.11',
    darkDefault: 'green.11',
  },
  attribute: {
    scopes: ['entity.other.attribute-name', 'meta.attribute'],
    lightDefault: 'blue.11',
    darkDefault: 'blue.11',
  },
  regexp: {
    scopes: ['string.regexp', 'constant.character.escape', 'constant.other.character-class.regexp'],
    lightDefault: 'blue.11',
    darkDefault: 'blue.11',
  },
};
