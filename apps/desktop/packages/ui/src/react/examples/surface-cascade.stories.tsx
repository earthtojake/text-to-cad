import { SURFACE_LEVELS, SURFACE_ROLES, SURFACE_SCOPES, SURFACE_STATUSES } from '@emdash/theme';
import type { SurfaceScopeName, SurfaceStatusName } from '@emdash/theme';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { AlertCircleIcon, AlertTriangleIcon, CheckCircle2Icon, InfoIcon } from 'lucide-react';
import React, { useState } from 'react';
import { Alert } from '../primitives/alert';
import { Box } from '../primitives/box';
import { Button } from '../primitives/button';
import { Input } from '../primitives/input';
import { Select } from '../primitives/select';
import { Surface } from '../primitives/surface/surface';
import { ThemeProvider } from '../primitives/theme-provider';
import { Toggle } from '../primitives/toggle';
import * as s from '../story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Examples/Surface Cascade',
  parameters: { layout: 'fullscreen' },
};

export default meta;
type Story = StoryObj;

/** Base / hover / selected swatches for a given direct-elevation CSS var prefix. */
function ElevationSwatch({ level, label }: { level: string; label: string }) {
  const isEmphasis = level.includes('emphasis');
  return (
    <Box display="flex" flexDirection="column" gap="1.5">
      <p className={cx(sx({ fontFamily: 'mono', color: 'foreground' }), s.text10px)}>{label}</p>
      <Box
        className={s.h10}
        width="full"
        rounded="sm"
        borderWidth="1"
        borderStyle="solid"
        borderColor="border"
        style={{ background: `var(--em-surface-${level})` }}
        title={`--surface-${level}`}
      />
      <Box
        className={s.h6}
        width="full"
        rounded="sm"
        style={{ background: `var(--em-surface-${level}-hover)` }}
        title={`--surface-${level}-hover`}
      />
      <Box
        className={s.h6}
        width="full"
        rounded="sm"
        style={{
          background: `var(--em-surface-${level}-selected)`,
          boxShadow: isEmphasis ? 'inset 0 0 0 1px var(--em-border-primary)' : undefined,
        }}
        title={`--surface-${level}-selected`}
      />
    </Box>
  );
}

function SurfaceCard({ level }: { level: SurfaceScopeName }) {
  return (
    <Box
      surface={level}
      display="flex"
      flexDirection="column"
      gap="3"
      rounded="lg"
      borderWidth="1"
      borderStyle="solid"
      borderColor="border"
      padding="4"
    >
      <p className={cx(sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foregroundMuted' }))}>
        .surface-{level}
      </p>
      <Input placeholder="Search…" />
      <Box display="flex" gap="2">
        <Button variant="ghost" size="base">
          Ghost
        </Button>
        <Button variant="primary" size="base">
          Primary
        </Button>
      </Box>
      <Select.Root>
        <Select.Trigger className={cx(sx({ width: 'full' }))}>
          <Select.Value placeholder="Pick one…" />
        </Select.Trigger>
        <Select.Content>
          <Select.Item value="a">Option A</Select.Item>
          <Select.Item value="b">Option B</Select.Item>
        </Select.Content>
      </Select.Root>
    </Box>
  );
}

function SurfaceTabs({ level }: { level: SurfaceScopeName }) {
  const [active, setActive] = useState('first');
  const tabs = [
    { id: 'first', label: 'First' },
    { id: 'second', label: 'Second' },
    { id: 'third', label: 'Third' },
  ];
  return (
    <Surface
      level={level}
      className={cx(
        sx({
          display: 'flex',
          flexDirection: 'column',
          gap: '0',
          rounded: 'lg',
          borderWidth: '1',
          borderStyle: 'solid',
          borderColor: 'border',
        })
      )}
    >
      <Box
        background="surface"
        display="flex"
        alignItems="center"
        gap="1"
        borderBottomWidth="1"
        borderStyle="solid"
        borderColor="border"
        px="1"
        paddingTop="1"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            data-active={active === tab.id ? 'true' : undefined}
            onClick={() => setActive(tab.id)}
            className={s.storyTabButton}
          >
            {tab.label}
          </button>
        ))}
      </Box>
      <Box surface="emphasis" roundedBottom="lg" padding="4">
        <p className={cx(sx({ fontSize: 'sm', color: 'foregroundMuted' }))}>
          Content for <strong className={cx(sx({ color: 'foreground' }))}>{active}</strong> tab on{' '}
          <code className={cx(sx({ fontFamily: 'mono', fontSize: 'xs' }))}>.surface-{level}</code>
        </p>
      </Box>
    </Surface>
  );
}

function SurfaceButtons({ level }: { level: SurfaceScopeName }) {
  return (
    <Surface
      level={level}
      className={cx(
        sx({
          display: 'flex',
          flexDirection: 'column',
          gap: '2',
          rounded: 'lg',
          borderWidth: '1',
          borderStyle: 'solid',
          borderColor: 'border',
          padding: '4',
        })
      )}
    >
      <p className={cx(sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foregroundMuted' }))}>
        .surface-{level}
      </p>
      <Box display="flex" flexWrap="wrap" gap="2">
        <Button variant="ghost">Ghost</Button>
        <Button variant="ghost" tone="destructive">
          Destructive
        </Button>
        <Button variant="ghost" tone="warning">
          Warning
        </Button>
        <Button variant="ghost" tone="info">
          Info
        </Button>
        <Button variant="ghost" tone="success">
          Success
        </Button>
      </Box>
      <Box display="flex" flexWrap="wrap" gap="2">
        <Button variant="primary">Primary</Button>
        <Button variant="primary" tone="destructive">
          Primary Destructive
        </Button>
      </Box>
    </Surface>
  );
}

/** One swatch per elevation step (base / hover / selected). */
export const Ladder: Story = {
  render: () => (
    <Box className={s.spaceY4} padding="6">
      <p className={cx(sx({ fontSize: 'sm', color: 'foregroundMuted' }))}>
        Swatches: base → hover → selected for each elevation.
      </p>
      <Box display="grid" className={s.cols5} gap="4">
        {SURFACE_LEVELS.map((level) => (
          <ElevationSwatch key={level} level={level} label={level} />
        ))}
      </Box>
    </Box>
  ),
};

/** Cascade proof: surface-emphasis card on each surface. */
export const Cascade: Story = {
  render: () => (
    <Box display="grid" className={s.cols3} gap="4" padding="6">
      {(['sunken', 'base', 'elevated'] as const).map((level) => (
        <Box
          key={level}
          surface={level}
          display="flex"
          flexDirection="column"
          gap="3"
          rounded="xl"
          padding="4"
        >
          <p className={cx(sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foregroundMuted' }))}>
            .surface-{level}
          </p>
          <Box surface="emphasis" rounded="lg" padding="3">
            <p className={cx(sx({ fontSize: 'xs', color: 'foregroundMuted' }))}>
              .surface-emphasis (card)
            </p>
            <p className={cx(sx({ marginTop: '1', fontSize: 'sm', color: 'foreground' }))}>
              Card content adapts automatically.
            </p>
          </Box>
        </Box>
      ))}
    </Box>
  ),
};

/** Components (Input, Button, Select) on every surface level. */
export const ComponentsOnAllSurfaces: Story = {
  render: () => (
    <Box display="grid" gap="4" padding="6" className={cx(s.cols2, s.lgCols3)}>
      {SURFACE_LEVELS.map((level) => (
        <SurfaceCard key={level} level={level} />
      ))}
    </Box>
  ),
};

/** Tab strips demonstrating hover and selected states on each surface. */
export const Tabs: Story = {
  render: () => (
    <Box display="grid" gap="4" padding="6" className={cx(s.cols1, s.lgCols2)}>
      {SURFACE_LEVELS.map((level) => (
        <SurfaceTabs key={level} level={level} />
      ))}
    </Box>
  ),
};

/** Buttons demonstrating hover, selected, and destructive across every surface. */
export const Buttons: Story = {
  render: () => (
    <Box display="grid" gap="4" padding="6" className={cx(s.cols1, s.lgCols2)}>
      {SURFACE_LEVELS.map((level) => (
        <SurfaceButtons key={level} level={level} />
      ))}
    </Box>
  ),
};

const STATUS_ICON: Record<SurfaceStatusName, React.ReactNode> = {
  info: <InfoIcon />,
  warning: <AlertTriangleIcon />,
  destructive: <AlertCircleIcon />,
  success: <CheckCircle2Icon />,
};

const STATUS_LABEL: Record<SurfaceStatusName, string> = {
  info: 'Info',
  warning: 'Warning',
  destructive: 'Destructive',
  success: 'Success',
};

const STATUS_MESSAGE: Record<SurfaceStatusName, string> = {
  info: 'This is an informational message. Ghost controls inside adapt to the tinted surface.',
  warning: 'Something needs your attention. Controls inherit the tinted hover/selected states.',
  destructive: 'This action cannot be undone. All controls respond to the destructive surface.',
  success: 'Operation completed successfully. Controls inherit the tinted hover/selected states.',
};

function StatusRoom({ status }: { status: SurfaceStatusName }) {
  const [pressed, setPressed] = useState(false);
  return (
    <Box display="flex" flexDirection="column" gap="3">
      <Alert.Root status={status} icon={STATUS_ICON[status]}>
        <strong>{STATUS_LABEL[status]}:</strong> {STATUS_MESSAGE[status]}
      </Alert.Root>
      <Box
        surface={status}
        display="flex"
        alignItems="center"
        gap="2"
        rounded="lg"
        borderWidth="1"
        borderStyle="solid"
        padding="3"
        style={{ borderColor: `var(--em-surface-${status}-border)` }}
      >
        <span
          className={cx(sx({ flex: '1', fontSize: 'sm' }))}
          style={{ color: `var(--em-surface-${status}-foreground)` }}
        >
          Controls inside a status surface
        </span>
        <Toggle
          pressed={pressed}
          onPressedChange={setPressed}
          className={cx(sx({ flexShrink: 0 }))}
        >
          {pressed ? 'Active' : 'Toggle'}
        </Toggle>
        <Button variant="ghost" tone="neutral">
          Action
        </Button>
        <Button variant="ghost" tone="destructive">
          Delete
        </Button>
      </Box>
    </Box>
  );
}

/**
 * Status surface variants (destructive / warning / info). Each is a tinted
 * "room" — ghost controls inside automatically pick up the tinted hover/selected
 * states from the cascade without any per-component override.
 */
export const StatusSurfaces: Story = {
  render: () => (
    <Box display="grid" className={s.cols1} gap="6" padding="6">
      <Box>
        <p className={cx(sx({ marginBottom: '1', fontSize: 'sm', color: 'foreground' }))}>
          Status surfaces — tinted rooms using the cascade
        </p>
        <p className={cx(sx({ fontSize: 'xs', color: 'foregroundMuted' }))}>
          Each status box rebinds{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>--surface-hover</code> and{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>--surface-selected</code> so any ghost
          Button / Toggle inside already hovers/selects with the correct tint.
        </p>
      </Box>
      {SURFACE_STATUSES.map((status) => (
        <StatusRoom key={status} status={status} />
      ))}
      <Box>
        <p
          className={cx(
            sx({
              marginBottom: '3',
              fontSize: 'sm',
              color: 'foregroundMuted',
            })
          )}
        >
          Swatches — base / hover / selected per status
        </p>
        <Box display="grid" className={s.cols3} gap="4">
          {SURFACE_STATUSES.map((status) => (
            <Box key={status} display="flex" flexDirection="column" gap="1.5">
              <p className={cx(sx({ fontFamily: 'mono', color: 'foreground' }), s.text10px)}>
                {status}
              </p>
              <Box
                className={s.h10}
                width="full"
                rounded="sm"
                borderWidth="1"
                borderStyle="solid"
                style={{
                  background: `var(--em-surface-${status})`,
                  borderColor: `var(--em-surface-${status}-border)`,
                }}
                title={`--surface-${status}`}
              />
              <Box
                className={s.h6}
                width="full"
                rounded="sm"
                style={{ background: `var(--em-surface-${status}-hover)` }}
                title={`--surface-${status}-hover`}
              />
              <Box
                className={s.h6}
                width="full"
                rounded="sm"
                style={{ background: `var(--em-surface-${status}-selected)` }}
                title={`--surface-${status}-selected`}
              />
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  ),
};

function PaperRoom() {
  return (
    <Box background="background" padding="6" className={s.spaceY6}>
      <Box>
        <p className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>
          Paper — primary content / tab background
        </p>
        <p
          className={cx(
            sx({ marginTop: '1', fontSize: 'xs', color: 'foregroundMuted' }),
            s.maxWProse
          )}
        >
          White-ish in light mode (matches{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>elevated</code>) and flat with{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>base</code> in dark mode. Use it for the
          surface tabbed content sits on. Cards/tabs on paper use{' '}
          <code className={cx(sx({ fontFamily: 'mono' }))}>base-emphasis</code>.
        </p>
      </Box>
      <div style={{ display: 'grid', gridTemplateColumns: '12rem 1fr', gap: '1.5rem' }}>
        <Box display="flex" flexDirection="column" gap="4">
          {SURFACE_ROLES.map((role) => (
            <ElevationSwatch key={role} level={role} label={role} />
          ))}
        </Box>
        <SurfaceTabs level="paper" />
      </div>
    </Box>
  );
}

/**
 * The `paper` surface role. Because it is white in light but base-gray in dark,
 * it is best understood side-by-side.
 */
export const Paper: Story = {
  render: () => (
    <Box display="flex" className={s.minHScreen}>
      <ThemeProvider theme="light" className={cx(sx({ flex: '1' }))}>
        <PaperRoom />
      </ThemeProvider>
      <ThemeProvider theme="dark" className={cx(sx({ flex: '1' }))}>
        <PaperRoom />
      </ThemeProvider>
    </Box>
  ),
};

/**
 * Status × Elevation matrix.
 *
 * Each cell renders a status room on a given elevation scope so you can
 * visually verify that the generated per-level tints track the canvas lightness
 * correctly. In dark mode each row should get progressively lighter left-to-right;
 * in light mode they should get slightly darker. The x1.0 track_delta is the
 * baseline — tune the shift multiplier in resolve.ts if rooms wash out.
 */
export const StatusLevelMatrix: Story = {
  render: () => (
    <Box display="flex" className={s.minHScreen}>
      {(['light', 'dark'] as const).map((theme) => (
        <ThemeProvider key={theme} theme={theme} className={cx(sx({ flex: '1', padding: '4' }))}>
          <Box background="background" padding="4" className={s.spaceY4}>
            <p
              className={cx(
                sx({
                  fontSize: 'sm',
                  color: 'foreground',
                  marginBottom: '3',
                })
              )}
            >
              {theme} — status × elevation
            </p>
            {SURFACE_STATUSES.map((status) => (
              <Box key={status} className={s.spaceY4}>
                <p
                  className={cx(
                    sx({ fontFamily: 'mono', fontSize: 'xs', color: 'foregroundMuted' })
                  )}
                >
                  {status}
                </p>
                <Box
                  display="grid"
                  gap="2"
                  style={{
                    gridTemplateColumns: `repeat(${SURFACE_SCOPES.length}, minmax(0, 1fr))`,
                  }}
                >
                  {SURFACE_SCOPES.map((scope) => {
                    const tokenBase =
                      scope === 'base' ? `--surface-${status}` : `--surface-${status}-${scope}`;
                    return (
                      <Box key={scope} display="flex" flexDirection="column" gap="1.5">
                        <p className={cx(sx({ fontFamily: 'mono' }), s.text10px)}>{scope}</p>
                        <Box
                          className={s.h10}
                          width="full"
                          rounded="sm"
                          borderWidth="1"
                          borderStyle="solid"
                          style={{
                            background: `var(${tokenBase})`,
                            borderColor: `var(${tokenBase}-border)`,
                          }}
                          title={tokenBase}
                        />
                        <Box
                          className={s.h6}
                          width="full"
                          rounded="sm"
                          style={{ background: `var(${tokenBase}-hover)` }}
                          title={`${tokenBase}-hover`}
                        />
                        <Box
                          className={s.h6}
                          width="full"
                          rounded="sm"
                          style={{ background: `var(${tokenBase}-selected)` }}
                          title={`${tokenBase}-selected`}
                        />
                      </Box>
                    );
                  })}
                </Box>
              </Box>
            ))}
          </Box>
        </ThemeProvider>
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
        className={cx(sx({ flex: '1', background: 'background', padding: '6' }), s.spaceY6)}
      >
        <p className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Light mode</p>
        <Box display="grid" className={s.cols3} gap="4">
          {SURFACE_LEVELS.map((level) => (
            <ElevationSwatch key={level} level={level} label={level} />
          ))}
        </Box>
        <Box display="grid" className={s.cols2} gap="3">
          {SURFACE_LEVELS.map((level) => (
            <SurfaceCard key={level} level={level} />
          ))}
        </Box>
      </ThemeProvider>
      <ThemeProvider
        defaultTheme="dark"
        className={cx(sx({ flex: '1', background: 'background', padding: '6' }), s.spaceY6)}
      >
        <p className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>Dark mode</p>
        <Box display="grid" className={s.cols3} gap="4">
          {SURFACE_LEVELS.map((level) => (
            <ElevationSwatch key={level} level={level} label={level} />
          ))}
        </Box>
        <Box display="grid" className={s.cols2} gap="3">
          {SURFACE_LEVELS.map((level) => (
            <SurfaceCard key={level} level={level} />
          ))}
        </Box>
      </ThemeProvider>
    </Box>
  ),
};
