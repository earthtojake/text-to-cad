import { SEMANTIC_VARS } from '@emdash/theme';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import React, { useEffect, useRef } from 'react';
import { Box } from '../primitives/box';
import { ThemeProvider } from '../primitives/theme-provider';
import * as s from '../story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

type Section = {
  title: string;
  match: (v: string) => boolean;
};

const SECTIONS: Section[] = [
  { title: 'Base backgrounds', match: (v) => /^--background(-[0-9])?$/.test(v) },
  {
    title: 'Secondary / tertiary / quaternary backgrounds',
    match: (v) =>
      v.startsWith('--background-secondary') ||
      v.startsWith('--background-tertiary') ||
      v.startsWith('--background-quaternary') ||
      v === '--background-neutral',
  },
  {
    title: 'Foregrounds',
    match: (v) =>
      v.startsWith('--foreground') &&
      !v.startsWith('--foreground-diff') &&
      !v.startsWith('--foreground-success') &&
      !v.startsWith('--foreground-error') &&
      !v.startsWith('--foreground-warning') &&
      !v.startsWith('--foreground-info') &&
      !v.startsWith('--foreground-destructive') &&
      v !== '--foreground-conflict' &&
      v !== '--foreground-merged',
  },
  {
    title: 'Borders',
    match: (v) =>
      v.startsWith('--border') &&
      !v.startsWith('--border-success') &&
      !v.startsWith('--border-error') &&
      !v.startsWith('--border-warning') &&
      !v.startsWith('--border-info'),
  },
  { title: 'Primary button', match: (v) => v.startsWith('--primary-button') },
  { title: 'Selection', match: (v) => v.startsWith('--selection') },
  { title: 'Status', match: (v) => v.startsWith('--status') },
  {
    title: 'Diff / VCS',
    match: (v) =>
      v.startsWith('--foreground-diff') ||
      v === '--foreground-conflict' ||
      v === '--foreground-merged',
  },
  {
    title: 'Success',
    match: (v) =>
      v.startsWith('--foreground-success') ||
      v.startsWith('--background-success') ||
      v.startsWith('--border-success'),
  },
  {
    title: 'Error / Destructive',
    match: (v) =>
      v.startsWith('--foreground-error') ||
      v.startsWith('--background-error') ||
      v.startsWith('--border-error') ||
      v.startsWith('--foreground-destructive') ||
      v.startsWith('--background-destructive') ||
      v.startsWith('--border-destructive'),
  },
  {
    title: 'Warning',
    match: (v) =>
      v.startsWith('--foreground-warning') ||
      v.startsWith('--background-warning') ||
      v.startsWith('--border-warning'),
  },
  {
    title: 'Info',
    match: (v) =>
      v.startsWith('--foreground-info') ||
      v.startsWith('--background-info') ||
      v.startsWith('--border-info'),
  },
];

function categorize(vars: readonly string[]): Array<{ title: string; tokens: string[] }> {
  const assigned = new Set<string>();
  const groups = SECTIONS.map(({ title, match }) => ({
    title,
    tokens: vars.filter((v) => {
      if (assigned.has(v)) return false;
      if (match(v)) {
        assigned.add(v);
        return true;
      }
      return false;
    }),
  }));
  const remaining = vars.filter((v) => !assigned.has(v));
  if (remaining.length > 0) groups.push({ title: 'Other', tokens: remaining });
  return groups.filter((g) => g.tokens.length > 0);
}

type TokenKind = 'foreground' | 'background' | 'border' | 'mixed';

function detectKind(varName: string): TokenKind {
  if (varName.startsWith('--foreground') || varName.startsWith('--status')) return 'foreground';
  if (
    varName.startsWith('--background') ||
    varName === '--selection' ||
    varName.startsWith('--primary-button-background')
  )
    return 'background';
  if (varName.startsWith('--border')) return 'border';
  return 'background';
}

function TokenRow({ varName }: { varName: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const kind = detectKind(varName);
  const resolvedRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (!ref.current || !resolvedRef.current) return;
    const computed = getComputedStyle(ref.current);
    if (kind === 'border') {
      resolvedRef.current.textContent = computed.borderColor;
    } else if (kind === 'foreground') {
      resolvedRef.current.textContent = computed.color;
    } else {
      resolvedRef.current.textContent = computed.backgroundColor;
    }
  });

  const preview =
    kind === 'foreground' ? (
      <Box
        ref={ref as React.Ref<HTMLElement>}
        display="flex"
        className={cx(s.h8, s.w16)}
        flexShrink={0}
        alignItems="center"
        justifyContent="center"
        rounded="sm"
        borderWidth="1"
        borderStyle="solid"
        borderColor="border"
        background="background"
        fontSize="sm"
        style={{ color: `var(${varName})` }}
      >
        Aa
      </Box>
    ) : kind === 'border' ? (
      <Box
        ref={ref as React.Ref<HTMLElement>}
        className={cx(s.h8, s.w16)}
        flexShrink={0}
        rounded="sm"
        background="background"
        style={{ border: `2px solid var(${varName})` }}
      />
    ) : (
      <Box
        ref={ref as React.Ref<HTMLElement>}
        className={cx(s.h8, s.w16)}
        flexShrink={0}
        rounded="sm"
        borderWidth="1"
        borderStyle="solid"
        borderColor="border"
        style={{ background: `var(${varName})` }}
      />
    );

  return (
    <Box display="flex" alignItems="center" gap="3" py="1.5">
      {preview}
      <Box display="flex" minWidth="0" flexDirection="column" gap="0.5">
        <span className={cx(sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foreground' }))}>
          {varName}
        </span>
        <span
          ref={resolvedRef}
          className={cx(sx({ fontFamily: 'mono', color: 'foregroundPassive' }), s.text10px)}
        />
      </Box>
    </Box>
  );
}

function SectionBlock({ title, tokens }: { title: string; tokens: string[] }) {
  return (
    <Box>
      <h3
        className={cx(
          sx({
            marginBottom: '2',
            borderBottomWidth: '1',
            borderStyle: 'solid',
            borderColor: 'border',
            paddingBottom: '1',
            color: 'foregroundMuted',
            textTransform: 'uppercase',
          }),
          s.text11px,
          s.trackingWider
        )}
      >
        {title}
      </h3>
      <Box display="grid" className={s.cols1} gap="0">
        {tokens.map((v) => (
          <TokenRow key={v} varName={v} />
        ))}
      </Box>
    </Box>
  );
}

function SemanticTokenGrid() {
  const groups = categorize(SEMANTIC_VARS);
  return (
    <Box display="flex" flexDirection="column" gap="8" background="background" padding="6">
      <Box>
        <h2 className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Semantic Color Tokens</h2>
        <p className={cx(sx({ marginTop: '1', fontSize: 'xs', color: 'foregroundMuted' }))}>
          Every semantic CSS custom property defined in{' '}
          <code
            className={cx(
              sx({ rounded: 'sm', background: 'background2', px: '1', fontFamily: 'mono' }),
              s.text11px
            )}
          >
            semantic-template.ts
          </code>
          . Foreground tokens show colored text; border tokens show a colored outline; all others
          show a filled swatch. Computed values update when the light/dark toolbar changes.
        </p>
      </Box>
      {groups.map((g) => (
        <SectionBlock key={g.title} title={g.title} tokens={g.tokens} />
      ))}
    </Box>
  );
}

const meta: Meta = {
  title: 'Theme/Semantic Tokens',
  parameters: { layout: 'fullscreen' },
};

export default meta;
type Story = StoryObj;

/** All semantic tokens grouped by category — responds to the Light / Dark toolbar. */
export const SemanticTokens: Story = {
  render: () => <SemanticTokenGrid />,
};

/** Light and dark semantic tokens side-by-side. */
export const BothModes: Story = {
  render: () => (
    <Box display="flex" className={s.minHScreen}>
      <ThemeProvider defaultTheme="light" className={cx(sx({ flex: '1', overflow: 'auto' }))}>
        <Box
          borderBottomWidth="1"
          borderStyle="solid"
          borderColor="border"
          background="background"
          px="6"
          py="3"
          fontSize="sm"
          color="foreground"
        >
          Light
        </Box>
        <SemanticTokenGrid />
      </ThemeProvider>
      <ThemeProvider defaultTheme="dark" className={cx(sx({ flex: '1', overflow: 'auto' }))}>
        <Box
          borderBottomWidth="1"
          borderStyle="solid"
          borderColor="border"
          background="background"
          px="6"
          py="3"
          fontSize="sm"
          color="foreground"
        >
          Dark
        </Box>
        <SemanticTokenGrid />
      </ThemeProvider>
    </Box>
  ),
};
