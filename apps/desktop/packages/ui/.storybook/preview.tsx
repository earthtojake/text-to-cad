import type { Decorator, Preview } from '@storybook/react-vite';
import React from 'react';
import { ThemeProvider } from '../src/react/primitives/theme-provider';
import type { ThemeId } from '../src/react/primitives/theme-provider';
// Third-party CSS loaded globally so all stories can rely on them without
// individual imports. Vite handles these in the Storybook build.
import 'devicon/devicon.min.css';
import 'katex/dist/katex.min.css';
import '@emdash/chat-ui/style.css';
import '../src/react/chat-ui/chat-theme.css';
// Opt-in element-defaults (body bg/fg, scrollbars, selection) using --em-* tokens.
import '../src/styles/base.css';

const SURFACE_FAMILIES = [
  'none',
  'sunken',
  'base',
  'base-emphasis',
  'elevated',
  'elevated-emphasis',
] as const;
type SurfaceFamily = (typeof SURFACE_FAMILIES)[number];

const withTheme: Decorator = (Story, context) => {
  const colorMode = (context.globals['colorMode'] as ThemeId) ?? 'light';
  const surface = (context.globals['surface'] as SurfaceFamily) ?? 'none';
  // Fullscreen stories own their layout — don't inject padding/min-height that
  // would stack on top of a story's own h-screen and overflow the viewport.
  const fullscreen = context.parameters?.['layout'] === 'fullscreen';

  const surfaceClass = surface !== 'none' ? `surface-${surface}` : '';
  // Set the design-system font on the frame (inline style) so story content wins
  // over Storybook's preview base body font; native controls pick it up via the
  // `font: inherit` reset in theme.base.css.
  const frameStyle: React.CSSProperties = fullscreen
    ? {
        height: '100vh',
        fontFamily: 'var(--em-font-sans)',
        backgroundColor: surface !== 'none' ? 'var(--em-surface)' : 'var(--em-background)',
      }
    : {
        minHeight: '100vh',
        padding: '2rem',
        fontFamily: 'var(--em-font-sans)',
        backgroundColor: surface !== 'none' ? 'var(--em-surface)' : 'var(--em-background)',
      };

  // ThemeProvider (default target="documentElement") applies the theme class to
  // <html> so portal-rendered elements inherit tokens automatically. All CSS is
  // loaded as side-effects by importing ThemeProvider — no separate CSS imports
  // are needed here.
  return (
    <ThemeProvider theme={colorMode} className={surfaceClass} style={frameStyle}>
      <Story />
    </ThemeProvider>
  );
};

const preview: Preview = {
  decorators: [withTheme],
  globalTypes: {
    colorMode: {
      description: 'Color mode',
      toolbar: {
        title: 'Color mode',
        icon: 'circlehollow',
        items: [
          { value: 'light', title: 'Light', icon: 'sun' },
          { value: 'dark', title: 'Dark', icon: 'moon' },
          { value: 'solarized-light', title: 'Solarized Light', icon: 'sun' },
          { value: 'solarized-dark', title: 'Solarized Dark', icon: 'moon' },
        ],
        dynamicTitle: true,
      },
    },
    surface: {
      description: 'Surface backdrop',
      toolbar: {
        title: 'Surface',
        icon: 'component',
        items: SURFACE_FAMILIES.map((s) => ({ value: s, title: s === 'none' ? 'Default' : s })),
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: {
    colorMode: 'light',
    surface: 'none',
  },
  parameters: {
    controls: { matchers: { color: /(background|color)$/i, date: /date/i } },
    docs: { codePanel: true },
  },
};

export default preview;
