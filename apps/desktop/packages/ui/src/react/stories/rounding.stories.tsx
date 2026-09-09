import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import React from 'react';
import { Box } from '../primitives/box';
import * as s from '../story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Theme/Rounding',
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

const RADIUS_TOKENS: Array<{ name: string; var: string; label: string }> = [
  { name: 'xs', var: '--radius-xs', label: '0.25rem / 4px' },
  { name: 'sm', var: '--radius-sm', label: '0.375rem / 6px' },
  { name: 'md', var: '--radius-md', label: '0.5rem / 8px' },
  { name: 'lg', var: '--radius-lg', label: '0.625rem / 10px' },
  { name: 'xl', var: '--radius-xl', label: '0.875rem / 14px' },
  { name: '2xl', var: '--radius-2xl', label: '1.25rem / 20px' },
  { name: 'full', var: '--radius-full', label: '9999px' },
];

/** All radius tokens with swatches showing the curvature. */
export const Scale: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="6" padding="4">
      <Box>
        <h2 className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Radius scale</h2>
        <p className={cx(sx({ marginTop: '1', fontSize: 'xs', color: 'foregroundMuted' }))}>
          Each swatch uses{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>border-radius: var(--em-radius-*)</code>.
          The anchor is <code className={cx(sx({ fontFamily: 'mono' }))}>--radius: 0.5rem</code>;
          change it to rescale the whole system.
        </p>
      </Box>
      <Box display="grid" gap="6" className={cx(s.cols4, s.lgCols7)}>
        {RADIUS_TOKENS.map(({ name, var: cssVar, label }) => (
          <Box key={name} display="flex" flexDirection="column" alignItems="center" gap="3">
            <Box
              background="surfaceBaseEmphasis"
              borderWidth="2"
              borderStyle="solid"
              borderColor="border"
              className={cx(s.h16, s.w16)}
              style={{ borderRadius: `var(${cssVar})` }}
            />
            <Box textAlign="center">
              <p
                className={cx(
                  sx({
                    fontFamily: 'mono',
                    fontSize: 'xs',
                    color: 'foreground',
                  })
                )}
              >
                {cssVar}
              </p>
              <p
                className={cx(
                  sx({ fontFamily: 'mono', color: 'foregroundPassive', marginTop: '0.5' }),
                  s.text10px
                )}
              >
                {label}
              </p>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  ),
};

/** Controls and inputs use the token scale. */
export const InContext: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="6" padding="4">
      <Box>
        <h2 className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Tokens in use</h2>
        <p className={cx(sx({ marginTop: '1', fontSize: 'xs', color: 'foregroundMuted' }))}>
          Buttons use <code className={cx(sx({ fontFamily: 'mono' }))}>--radius-lg</code> (base) and{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>--radius-md</code> (sm). Inputs use{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>--radius-md</code>.
        </p>
      </Box>
      <Box display="flex" flexWrap="wrap" alignItems="center" gap="3">
        <button
          type="button"
          className={cx(
            sx({
              background: 'surfaceHover',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '1.5',
              rounded: 'lg',
              borderWidth: '1',
              borderStyle: 'solid',
              borderColor: 'transparent',
              px: '2.5',
              fontSize: 'sm',
              color: 'foreground',
            }),
            s.h8
          )}
        >
          Base button (--radius-lg)
        </button>
        <button
          type="button"
          className={cx(
            sx({
              background: 'surfaceHover',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '1',
              rounded: 'md',
              borderWidth: '1',
              borderStyle: 'solid',
              borderColor: 'transparent',
              px: '2',
              fontSize: 'xs',
              color: 'foreground',
            }),
            s.h6
          )}
        >
          SM button (--radius-md)
        </button>
        <input
          type="text"
          placeholder="Input (--radius-md)"
          className={cx(
            sx({
              background: 'surface',
              rounded: 'md',
              borderWidth: '1',
              borderStyle: 'solid',
              borderColor: 'border',
              px: '2.5',
              fontSize: 'sm',
              color: 'foreground',
            }),
            s.h8,
            s.outlineNone
          )}
        />
      </Box>
    </Box>
  ),
};
