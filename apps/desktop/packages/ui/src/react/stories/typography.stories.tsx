import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import React from 'react';
import { Box } from '../primitives/box';
import { ThemeProvider } from '../primitives/theme-provider';
import { Heading } from '../primitives/typography/Heading';
import { Text } from '../primitives/typography/Text';
import { textVariants, type TextVariantProps } from '../primitives/typography/typography.variants';
import * as s from '../story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Theme/Typography',
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

const SIZE_TOKENS = [
  { name: '--text-micro', size: '10px', lh: '1.2' },
  { name: '--text-tiny', size: '11px', lh: '1.3' },
  { name: '--text-xs', size: '12px', lh: '1.5' },
  { name: '--text-sm', size: '13px', lh: '1.5' },
  { name: '--text-base', size: '14px', lh: '1.5' },
  { name: '--text-lg', size: '17px', lh: '1.5' },
  { name: '--text-xl', size: '20px', lh: '1.4' },
  { name: '--text-2xl', size: '24px', lh: '1.3' },
];

const WEIGHT_TOKENS = [{ name: '--font-weight-normal', value: 400, label: 'Normal 400' }];

/** Primitive type size scale — each --text-* token. */
export const TypeScale: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2" padding="4">
      <Box marginBottom="4">
        <h2 className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Type size scale</h2>
        <p className={cx(sx({ marginTop: '1', fontSize: 'xs', color: 'foregroundMuted' }))}>
          Primitive <code className={cx(sx({ fontFamily: 'mono' }))}>--text-*</code> tokens.
          Semantic{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>--type-&lt;role&gt;-font-size</code>{' '}
          values reference these.
        </p>
      </Box>
      {SIZE_TOKENS.map(({ name, size, lh }) => (
        <Box key={name} display="flex" alignItems="baseline" gap="4">
          <Box
            display="flex"
            flexDirection="column"
            flexShrink={0}
            className={s.w48}
            style={{ textAlign: 'right' }}
          >
            <code
              className={cx(sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foregroundPassive' }))}
            >
              {name}
            </code>
            <span className={cx(sx({ fontSize: 'xs', color: 'foregroundPassive' }))}>
              {size} / {lh}
            </span>
          </Box>
          <span
            style={{ fontSize: `var(${name})`, lineHeight: `var(${name}--line-height, ${lh})` }}
            className={cx(sx({ color: 'foreground' }))}
          >
            The quick brown fox jumps over the lazy dog.
          </span>
        </Box>
      ))}
    </Box>
  ),
};

/** Font weight scale — each --font-weight-* token. */
export const Weights: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="4" padding="4">
      <Box marginBottom="2">
        <h2 className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Font weight scale</h2>
        <p className={cx(sx({ marginTop: '1', fontSize: 'xs', color: 'foregroundMuted' }))}>
          Primitive <code className={cx(sx({ fontFamily: 'mono' }))}>--font-weight-*</code> tokens.
        </p>
      </Box>
      {WEIGHT_TOKENS.map(({ name, value, label }) => (
        <Box key={name} display="flex" alignItems="baseline" gap="4">
          <Box
            display="flex"
            flexDirection="column"
            flexShrink={0}
            className={s.w48}
            style={{ textAlign: 'right' }}
          >
            <code
              className={cx(sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foregroundPassive' }))}
            >
              {name}
            </code>
            <span className={cx(sx({ fontSize: 'xs', color: 'foregroundPassive' }))}>{value}</span>
          </Box>
          <span
            style={{ fontWeight: `var(${name})`, fontSize: '14px' }}
            className={cx(sx({ color: 'foreground' }))}
          >
            {label}: The quick brown fox jumps over the lazy dog.
          </span>
        </Box>
      ))}
    </Box>
  ),
};

const ROLES: Array<{ label: string; variant: TextVariantProps['variant']; as?: string }> = [
  { label: 'h1 — 20px / 400', variant: 'h1', as: 'p' },
  { label: 'h2 — 17px / 400', variant: 'h2', as: 'p' },
  { label: 'h3 — 14px / 400', variant: 'h3', as: 'p' },
  { label: 'section — 13px / 400', variant: 'section', as: 'p' },
  { label: 'body — 14px / 400', variant: 'body', as: 'p' },
  { label: 'bodyItalic — 14px / 400 italic', variant: 'bodyItalic', as: 'p' },
  { label: 'bodyLink — 14px / 400', variant: 'bodyLink', as: 'p' },
  { label: 'caption — 12px / 400', variant: 'caption', as: 'p' },
  { label: 'description — 13px / 400', variant: 'description', as: 'p' },
  { label: 'inlineCode — 12px / 400 mono', variant: 'inlineCode', as: 'p' },
  { label: 'code — 13px / 400 mono', variant: 'code', as: 'p' },
  { label: 'codeLang — 11px / 400 sans', variant: 'codeLang', as: 'p' },
  { label: 'mention — 14px / 400', variant: 'mention', as: 'p' },
];

/** Every typography role applied to a sample sentence. */
export const AllRoles: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="4">
      {ROLES.map(({ label, variant }) => (
        <Box key={variant} display="flex" alignItems="baseline" gap="4">
          <span
            className={cx(
              sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foregroundPassive', flexShrink: 0 }),
              s.w52
            )}
          >
            {label}
          </span>
          <Text as="p" variant={variant} tone="default">
            The quick brown fox jumps over the lazy dog.
          </Text>
        </Box>
      ))}
    </Box>
  ),
};

/** Heading component: levels 1–4. */
export const Headings: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3">
      <Heading level={1}>Heading level 1 — 20px / 400</Heading>
      <Heading level={2}>Heading level 2 — 17px / 400</Heading>
      <Heading level={3}>Heading level 3 — 14px / 400</Heading>
      <Heading level={4}>Heading level 4 — 13px / 400</Heading>
    </Box>
  ),
};

/** Tone variants — default, muted, passive. */
export const Tones: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2">
      {(['default', 'muted', 'passive'] as const).map((tone) => (
        <Text key={tone} as="p" variant="body" tone={tone}>
          tone="{tone}": The quick brown fox jumps over the lazy dog.
        </Text>
      ))}
    </Box>
  ),
};

/** className extension — role + extra utility classes. */
export const ClassExtension: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2">
      <Text
        as="p"
        variant="body"
        className={cx(sx({ fontStyle: 'italic', textDecoration: 'underline' }))}
      >
        className extension: italic + underline applied after role.
      </Text>
      <Heading level={2} className={cx(sx({ color: 'foregroundMuted' }))}>
        Muted h2 via className
      </Heading>
    </Box>
  ),
};

/** textVariants recipe used directly (no component wrapper). */
export const RecipeDirectUse: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2">
      <p className={textVariants({ variant: 'h1', tone: 'default' })}>
        textVariants — h1 role, default tone
      </p>
      <p className={textVariants({ variant: 'body', tone: 'muted' })}>
        textVariants — body role, muted tone
      </p>
    </Box>
  ),
};

/** All surfaces side-by-side to confirm readability. */
export const AllSurfaces: Story = {
  render: () => (
    <Box display="grid" className={s.cols5} gap="3">
      {(['sunken', 'base', 'base-emphasis', 'elevated', 'elevated-emphasis'] as const).map((sv) => (
        <Box key={sv} surface={sv} rounded="lg" padding="4">
          <p
            className={cx(
              sx({
                marginBottom: '1',
                fontFamily: 'mono',
                fontSize: 'xs',
                color: 'foregroundPassive',
              })
            )}
          >
            .surface-{sv}
          </p>
          <Heading level={2} className={cx(sx({ marginBottom: '1' }))}>
            Heading
          </Heading>
          <Text as="p" variant="body" tone="default">
            Body text on this surface.
          </Text>
          <Text as="p" variant="body" tone="muted">
            Muted body text.
          </Text>
        </Box>
      ))}
    </Box>
  ),
};

/** Light and dark modes side-by-side. */
export const BothModes: Story = {
  render: () => (
    <Box display="flex" className={cx(s.minHScreen, s.divideX, s.divideBorder)}>
      <ThemeProvider
        defaultTheme="light"
        className={cx(sx({ flex: '1', background: 'background', padding: '8' }))}
      >
        <Heading level={1} className={cx(sx({ marginBottom: '2' }))}>
          Light mode
        </Heading>
        <Text as="p" variant="body" tone="default" className={cx(sx({ marginBottom: '1' }))}>
          Body text
        </Text>
        <Text as="p" variant="body" tone="muted">
          Muted body text
        </Text>
      </ThemeProvider>
      <ThemeProvider
        defaultTheme="dark"
        className={cx(sx({ flex: '1', background: 'background', padding: '8' }))}
      >
        <Heading level={1} className={cx(sx({ marginBottom: '2' }))}>
          Dark mode
        </Heading>
        <Text as="p" variant="body" tone="default" className={cx(sx({ marginBottom: '1' }))}>
          Body text
        </Text>
        <Text as="p" variant="body" tone="muted">
          Muted body text
        </Text>
      </ThemeProvider>
    </Box>
  ),
};
