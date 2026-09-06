import { Box } from '@react/primitives/box';
import { ThemeProvider } from '@react/primitives/theme-provider';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { Surface } from '@/react/primitives/surface/surface';
import { ScrollContainer } from '.';
import * as s from '@react/story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

const SURFACE_LEVELS = [
  'sunken',
  'base',
  'base-emphasis',
  'elevated',
  'elevated-emphasis',
] as const;

const meta: Meta<typeof ScrollContainer> = {
  title: 'Primitives/ScrollContainer',
  component: ScrollContainer,
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj<typeof ScrollContainer>;

function Paragraph({ n = 1 }: { n?: number }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <p key={i} className={cx(sx({ fontSize: 'sm', color: 'foreground' }))}>
          Paragraph {i + 1}. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
          tempor incididunt ut labore et dolore magna aliqua.
        </p>
      ))}
    </>
  );
}

/**
 * Content overflows — the top fade appears once you scroll down. At rest
 * (scrolled to the top) no fade shows.
 */
export const WithOverflow: Story = {
  render: () => (
    <ScrollContainer
      maxHeight={192}
      className={cx(
        sx({
          background: 'surface',
          borderWidth: '1',
          borderStyle: 'solid',
          borderColor: 'border',
          rounded: 'sm',
        }),
        s.w80
      )}
    >
      <Box display="flex" flexDirection="column" gap="3" padding="4">
        <Paragraph n={8} />
      </Box>
    </ScrollContainer>
  ),
};

/**
 * Content fits — no fade appears because the scroll timeline stays inactive
 * when there is no overflow.
 */
export const NoOverflow: Story = {
  render: () => (
    <ScrollContainer
      maxHeight={192}
      className={cx(
        sx({
          background: 'surface',
          borderWidth: '1',
          borderStyle: 'solid',
          borderColor: 'border',
          rounded: 'sm',
        }),
        s.w80
      )}
    >
      <Box display="flex" flexDirection="column" gap="3" padding="4">
        <Paragraph n={2} />
      </Box>
    </ScrollContainer>
  ),
};

/** Top fade disabled — scrollable, but no fade appears after scrolling down. */
export const TopFadeDisabled: Story = {
  render: () => (
    <ScrollContainer
      maxHeight={192}
      topFade={false}
      className={cx(
        sx({
          background: 'surface',
          borderWidth: '1',
          borderStyle: 'solid',
          borderColor: 'border',
          rounded: 'sm',
        }),
        s.w80
      )}
    >
      <Box display="flex" flexDirection="column" gap="3" padding="4">
        <Paragraph n={8} />
      </Box>
    </ScrollContainer>
  ),
};

/** String maxHeight — CSS value passed directly (e.g. '50vh'). */
export const MaxHeightString: Story = {
  render: () => (
    <ScrollContainer
      maxHeight="50vh"
      className={cx(
        sx({
          background: 'surface',
          borderWidth: '1',
          borderStyle: 'solid',
          borderColor: 'border',
          rounded: 'sm',
        }),
        s.w80
      )}
    >
      <Box display="flex" flexDirection="column" gap="3" padding="4">
        <Paragraph n={16} />
      </Box>
    </ScrollContainer>
  ),
};

/**
 * All surface elevations side-by-side — the mask-based fade is color-agnostic
 * (it clips content alpha rather than overlaying a color), so it works correctly
 * on every surface without any per-surface configuration.
 */
export const SurfaceAware: Story = {
  render: () => (
    <Box display="flex" flexWrap="wrap" gap="4">
      {SURFACE_LEVELS.map((level) => (
        <Surface key={level} level={level} className={cx(sx({ rounded: 'lg', padding: '4' }))}>
          <p className={cx(sx({ marginBottom: '2', fontSize: 'xs', color: 'foregroundMuted' }))}>
            .surface-{level}
          </p>
          <ScrollContainer
            maxHeight={160}
            className={cx(
              sx({
                background: 'surface',
                borderWidth: '1',
                borderStyle: 'solid',
                borderColor: 'border',
                rounded: 'sm',
              }),
              s.w44
            )}
          >
            <Box display="flex" flexDirection="column" gap="3" padding="3">
              <Paragraph n={8} />
            </Box>
          </ScrollContainer>
        </Surface>
      ))}
    </Box>
  ),
};

/** Light and dark side-by-side — the mask-based top fade works identically in both modes. */
export const BothModes: Story = {
  render: () => (
    <Box display="flex" className={cx(s.minHScreen, s.divideX, s.divideBorder)}>
      <ThemeProvider
        defaultTheme="light"
        className={cx(sx({ flex: '1', background: 'background', padding: '8' }))}
      >
        <p className={cx(sx({ marginBottom: '4', fontSize: 'sm', color: 'foreground' }))}>
          Light mode
        </p>
        <ScrollContainer
          maxHeight={192}
          className={cx(
            sx({
              background: 'surface',
              borderWidth: '1',
              borderStyle: 'solid',
              borderColor: 'border',
              rounded: 'sm',
            }),
            s.w80
          )}
        >
          <Box display="flex" flexDirection="column" gap="3" padding="4">
            <Paragraph n={8} />
          </Box>
        </ScrollContainer>
      </ThemeProvider>
      <ThemeProvider
        defaultTheme="dark"
        className={cx(sx({ flex: '1', background: 'background', padding: '8' }))}
      >
        <p className={cx(sx({ marginBottom: '4', fontSize: 'sm', color: 'foreground' }))}>
          Dark mode
        </p>
        <ScrollContainer
          maxHeight={192}
          className={cx(
            sx({
              background: 'surface',
              borderWidth: '1',
              borderStyle: 'solid',
              borderColor: 'border',
              rounded: 'sm',
            }),
            s.w80
          )}
        >
          <Box display="flex" flexDirection="column" gap="3" padding="4">
            <Paragraph n={8} />
          </Box>
        </ScrollContainer>
      </ThemeProvider>
    </Box>
  ),
};
