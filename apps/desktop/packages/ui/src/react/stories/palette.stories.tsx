import { SCALE_NAMES, STEPS } from '@emdash/theme';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import React, { useEffect, useRef, useState } from 'react';
import { Box } from '../primitives/box';
import { ThemeProvider } from '../primitives/theme-provider';
import * as s from '../story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

type ScaleName = (typeof SCALE_NAMES)[number];

function StepSwatch({ scale, step }: { scale: ScaleName; step: number }) {
  const varName = `--${scale}-${step}`;
  const ref = useRef<HTMLDivElement>(null);
  const [resolved, setResolved] = useState('');

  useEffect(() => {
    if (ref.current) {
      const val = getComputedStyle(ref.current).backgroundColor;
      setResolved((prev) => (val !== prev ? val : prev));
    }
  }, []);

  const isStep9 = step === 9;

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      gap="1"
      title={`${varName}\n${resolved}`}
    >
      <Box
        ref={ref as React.Ref<HTMLElement>}
        className={s.h10}
        width="full"
        rounded="sm"
        style={{
          background: `var(${varName})`,
          boxShadow: isStep9
            ? '0 0 0 2px var(--em-background), 0 0 0 4px var(--em-border-primary)'
            : undefined,
        }}
      />
      <span
        className={cx(
          sx({ fontFamily: 'mono', lineHeight: 'none', color: 'foregroundPassive' }),
          s.text9px
        )}
      >
        {step}
      </span>
    </Box>
  );
}

function ContrastSwatch({ scale }: { scale: ScaleName }) {
  const ref = useRef<HTMLDivElement>(null);
  const [resolved, setResolved] = useState('');

  useEffect(() => {
    if (ref.current) {
      const val = getComputedStyle(ref.current).backgroundColor;
      setResolved((prev) => (val !== prev ? val : prev));
    }
  }, []);

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      gap="1"
      title={`--${scale}-contrast\n${resolved}`}
    >
      <Box
        ref={ref as React.Ref<HTMLElement>}
        className={s.h10}
        width="full"
        rounded="sm"
        style={{
          background: `var(--${scale}-contrast)`,
          outline: '1px solid var(--em-border)',
        }}
      />
      <span
        className={cx(
          sx({ fontFamily: 'mono', lineHeight: 'none', color: 'foregroundPassive' }),
          s.text9px
        )}
      >
        ctrst
      </span>
    </Box>
  );
}

function ScaleRow({ scale }: { scale: ScaleName }) {
  return (
    <Box display="flex" alignItems="flex-start" gap="2">
      <Box paddingTop="3" flexShrink={0} className={s.w16}>
        <span className={cx(sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foreground' }))}>
          {scale}
        </span>
      </Box>

      <Box display="grid" flex="1" className={cx(s.cols12)} gap="1">
        {STEPS.map((step) => (
          <StepSwatch key={step} scale={scale} step={step} />
        ))}
      </Box>

      <Box flexShrink={0} className={s.w12}>
        <ContrastSwatch scale={scale} />
      </Box>
    </Box>
  );
}

function HeaderRow() {
  return (
    <Box display="flex" alignItems="center" gap="2">
      <Box flexShrink={0} className={s.w16} />
      <Box display="grid" flex="1" className={s.cols12} gap="1">
        {STEPS.map((step) => (
          <div
            key={step}
            className={cx(
              sx({ textAlign: 'center', fontFamily: 'mono', color: 'foregroundPassive' }),
              s.text9px
            )}
          >
            {step}
          </div>
        ))}
      </Box>
      <Box
        flexShrink={0}
        className={cx(s.w12, s.text9px)}
        style={{
          textAlign: 'center',
          fontFamily: 'var(--em-font-mono)',
          color: 'var(--em-foreground-passive)',
        }}
      >
        C
      </Box>
    </Box>
  );
}

function PaletteGrid() {
  return (
    <Box display="flex" flexDirection="column" gap="3" background="background" padding="6">
      <Box marginBottom="2">
        <h2 className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Color Palette</h2>
        <p className={cx(sx({ marginTop: '1', fontSize: 'xs', color: 'foregroundMuted' }))}>
          Generated from OKLCH hue seeds with APCA-targeted contrast. Step 9 (ringed) is the solid
          fill. &quot;C&quot; is the auto-selected contrast text color for use on step 9. Hover a
          swatch for the CSS variable name and computed value.
        </p>
      </Box>
      <HeaderRow />
      <Box display="flex" flexDirection="column" gap="2">
        {SCALE_NAMES.map((scale) => (
          <ScaleRow key={scale} scale={scale} />
        ))}
      </Box>
    </Box>
  );
}

const meta: Meta = {
  title: 'Theme/Palette',
  parameters: { layout: 'fullscreen' },
};

export default meta;
type Story = StoryObj;

/** All palette scales — responds to the Light / Dark toolbar. */
export const Palette: Story = {
  render: () => <PaletteGrid />,
};

/** Light and dark palettes rendered side-by-side for visual parity check. */
export const BothModes: Story = {
  render: () => (
    <Box display="flex" className={s.minHScreen}>
      <ThemeProvider defaultTheme="light" className={cx(sx({ flex: '1' }))}>
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
        <PaletteGrid />
      </ThemeProvider>
      <ThemeProvider defaultTheme="dark" className={cx(sx({ flex: '1' }))}>
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
        <PaletteGrid />
      </ThemeProvider>
    </Box>
  ),
};
