/**
 * bundled-themes.ts — chat-ui owned copy of the emdash Shiki themes.
 *
 * These theme objects are replicated from @emdash/ui/theme/shiki-themes
 * so that the default ChatHighlighter in this package does not need to import
 * from @emdash/ui at runtime. The values must stay in sync with the generated
 * shiki-themes.ts when the design token palette is regenerated.
 */

export const BUNDLED_LIGHT_THEME = {
  name: 'em-light',
  type: 'light',
  colors: {
    'editor.background': '#fcfcfc',
    'editor.foreground': '#222122',
    'editor.selectionBackground': '#9cc8fa40',
    'editor.lineHighlightBackground': '#f1f1f1',
    'editorCursor.foreground': '#222122',
    'editor.findMatchBackground': '#9cc8fa60',
    'editor.findMatchHighlightBackground': '#9cc8fa30',
    'editorLineNumber.foreground': '#8e8d8d',
    'editorLineNumber.activeForeground': '#222122',
    'editorIndentGuide.background': '#cfcfcf',
    'editorBracketMatch.background': '#c9dcf3',
    'editorBracketMatch.border': '#99d2ff',
    'scrollbarSlider.background': '#c5c4c460',
    'scrollbarSlider.hoverBackground': '#cfcece80',
  },
  tokenColors: [
    {
      scope: ['comment', 'punctuation.definition.comment', 'string.comment'],
      settings: { foreground: '#8e8d8d', fontStyle: 'italic' },
    },
    {
      scope: [
        'keyword',
        'storage.type',
        'storage.modifier',
        'keyword.control',
        'keyword.operator.new',
        'keyword.other.using',
        'keyword.other.import',
        'keyword.other.package',
      ],
      settings: { foreground: '#9d4241' },
    },
    {
      scope: [
        'string',
        'string.quoted',
        'string.template',
        'string.interpolated',
        'punctuation.definition.string',
      ],
      settings: { foreground: '#2263a4' },
    },
    {
      scope: ['constant.numeric', 'constant.language', 'constant.character', 'constant.other'],
      settings: { foreground: '#2263a4' },
    },
    {
      scope: [
        'entity.name.function',
        'support.function',
        'meta.function-call',
        'variable.function',
      ],
      settings: { foreground: '#006f51' },
    },
    {
      scope: [
        'entity.name.type',
        'entity.name.class',
        'entity.name.namespace',
        'entity.name.enum',
        'entity.name.interface',
        'support.class',
        'support.type',
      ],
      settings: { foreground: '#7e5100' },
    },
    {
      scope: ['variable', 'variable.other', 'variable.parameter', 'meta.definition.variable'],
      settings: { foreground: '#222122' },
    },
    {
      scope: [
        'variable.other.property',
        'variable.other.object.property',
        'support.variable.property',
        'meta.object-literal.key',
      ],
      settings: { foreground: '#626161' },
    },
    {
      scope: [
        'keyword.operator',
        'punctuation.accessor',
        'punctuation.separator',
        'meta.brace',
        'punctuation',
      ],
      settings: { foreground: '#848283' },
    },
    {
      scope: ['entity.name.tag', 'meta.tag', 'punctuation.definition.tag'],
      settings: { foreground: '#1f6e30' },
    },
    {
      scope: ['entity.other.attribute-name', 'meta.attribute'],
      settings: { foreground: '#2263a4' },
    },
    {
      scope: [
        'string.regexp',
        'constant.character.escape',
        'constant.other.character-class.regexp',
      ],
      settings: { foreground: '#2263a4' },
    },
  ],
  semanticHighlighting: true,
} as const;

export const BUNDLED_DARK_THEME = {
  name: 'em-dark',
  type: 'dark',
  colors: {
    'editor.background': '#111111',
    'editor.foreground': '#e9e9e9',
    'editor.selectionBackground': '#10396240',
    'editor.lineHighlightBackground': '#181818',
    'editorCursor.foreground': '#e9e9e9',
    'editor.findMatchBackground': '#10396260',
    'editor.findMatchHighlightBackground': '#10396230',
    'editorLineNumber.foreground': '#929091',
    'editorLineNumber.activeForeground': '#e9e9e9',
    'editorIndentGuide.background': '#302f30',
    'editorBracketMatch.background': '#1a293a',
    'editorBracketMatch.border': '#25619e',
    'scrollbarSlider.background': '#38383860',
    'scrollbarSlider.hoverBackground': '#62616180',
  },
  tokenColors: [
    {
      scope: ['comment', 'punctuation.definition.comment', 'string.comment'],
      settings: { foreground: '#929091', fontStyle: 'italic' },
    },
    {
      scope: [
        'keyword',
        'storage.type',
        'storage.modifier',
        'keyword.control',
        'keyword.operator.new',
        'keyword.other.using',
        'keyword.other.import',
        'keyword.other.package',
      ],
      settings: { foreground: '#ff9c98' },
    },
    {
      scope: [
        'string',
        'string.quoted',
        'string.template',
        'string.interpolated',
        'punctuation.definition.string',
      ],
      settings: { foreground: '#7cbcff' },
    },
    {
      scope: ['constant.numeric', 'constant.language', 'constant.character', 'constant.other'],
      settings: { foreground: '#7cbcff' },
    },
    {
      scope: [
        'entity.name.function',
        'support.function',
        'meta.function-call',
        'variable.function',
      ],
      settings: { foreground: '#4fcca8' },
    },
    {
      scope: [
        'entity.name.type',
        'entity.name.class',
        'entity.name.namespace',
        'entity.name.enum',
        'entity.name.interface',
        'support.class',
        'support.type',
      ],
      settings: { foreground: '#dead52' },
    },
    {
      scope: ['variable', 'variable.other', 'variable.parameter', 'meta.definition.variable'],
      settings: { foreground: '#e9e9e9' },
    },
    {
      scope: [
        'variable.other.property',
        'variable.other.object.property',
        'support.variable.property',
        'meta.object-literal.key',
      ],
      settings: { foreground: '#b8b7b8' },
    },
    {
      scope: [
        'keyword.operator',
        'punctuation.accessor',
        'punctuation.separator',
        'meta.brace',
        'punctuation',
      ],
      settings: { foreground: '#a09f9f' },
    },
    {
      scope: ['entity.name.tag', 'meta.tag', 'punctuation.definition.tag'],
      settings: { foreground: '#7dc986' },
    },
    {
      scope: ['entity.other.attribute-name', 'meta.attribute'],
      settings: { foreground: '#7cbcff' },
    },
    {
      scope: [
        'string.regexp',
        'constant.character.escape',
        'constant.other.character-class.regexp',
      ],
      settings: { foreground: '#7cbcff' },
    },
  ],
  semanticHighlighting: true,
} as const;
