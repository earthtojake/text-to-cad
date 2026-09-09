import { Box } from '@react/primitives/box';
import { Button, type ButtonVariant } from '@react/primitives/button';
import { Kbd, KbdGroup } from '@react/primitives/kbd';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { PlusIcon, SearchIcon, TrashIcon } from 'lucide-react';
import * as s from '@react/story-layout.css';

const buttonVariants: ButtonVariant[] = ['primary', 'destructive', 'secondary', 'ghost', 'link'];

const meta: Meta<typeof Button> = {
  title: 'Primitives/Button',
  component: Button,
  parameters: { layout: 'centered' },
  argTypes: {
    variant: { control: 'select', options: buttonVariants },
    tone: { table: { disable: true } },
    size: { control: 'select', options: ['xs', 'sm', 'base', 'lg'] },
    icon: { control: 'boolean' },
    disabled: { control: 'boolean' },
  },
};

export default meta;
type Story = StoryObj<typeof Button>;

export const Default: Story = {
  args: { children: 'Button', variant: 'primary' },
};

/** Public button variants. */
export const VariantMatrix: Story = {
  render: () => (
    <Box display="flex" flexWrap="wrap" alignItems="center" gap="2">
      {buttonVariants.map((variant) => (
        <Button key={variant} variant={variant}>
          {variant}
        </Button>
      ))}
    </Box>
  ),
};

/** The four-step size scale — XS (24 px), SM (28 px), Base (32 px), LG (40 px) — plus link. */
export const Sizes: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3">
      <Box display="flex" flexWrap="wrap" alignItems="flex-end" gap="2">
        <Button variant="primary" size="xs">
          Extra small
        </Button>
        <Button variant="primary" size="sm">
          Small
        </Button>
        <Button variant="primary" size="base">
          Base
        </Button>
        <Button variant="primary" size="lg">
          Large
        </Button>
        <Button variant="link">Link</Button>
      </Box>
      <Box display="flex" flexWrap="wrap" alignItems="flex-end" gap="2">
        <Button size="xs" icon>
          <SearchIcon />
        </Button>
        <Button size="sm" icon>
          <SearchIcon />
        </Button>
        <Button size="base" icon>
          <SearchIcon />
        </Button>
        <Button size="lg" icon>
          <SearchIcon />
        </Button>
      </Box>
    </Box>
  ),
};

/** Icon-only icon buttons. */
export const IconButtons: Story = {
  render: () => (
    <Box display="flex" flexWrap="wrap" alignItems="center" gap="2">
      <Button icon variant="ghost">
        <PlusIcon />
      </Button>
      <Button icon variant="primary">
        <PlusIcon />
      </Button>
      <Button icon variant="secondary" size="xs">
        <SearchIcon />
      </Button>
      <Button icon variant="destructive">
        <TrashIcon />
      </Button>
    </Box>
  ),
};

/** Disabled state. */
export const Disabled: Story = {
  render: () => (
    <Box display="flex" flexWrap="wrap" alignItems="center" gap="2">
      {buttonVariants.map((variant) => (
        <Button key={variant} variant={variant} disabled>
          {variant}
        </Button>
      ))}
    </Box>
  ),
};

/** Surface-relative hover / active adapt correctly across all backgrounds. */
export const AcrossSurfaces: Story = {
  render: () => (
    <Box
      background="surfaceSunken"
      display="flex"
      flexDirection="column"
      gap="4"
      rounded="xl"
      padding="4"
    >
      {(['sunken', 'base', 'base-emphasis', 'elevated', 'elevated-emphasis'] as const).map(
        (level) => (
          <Box
            key={level}
            surface={level}
            display="flex"
            flexWrap="wrap"
            alignItems="center"
            gap="2"
            rounded="lg"
            padding="3"
          >
            <span
              className={s.w36}
              style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}
            >
              {level}
            </span>
            <Button variant="primary">Primary</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="link">Link</Button>
            <Button icon>
              <SearchIcon />
            </Button>
          </Box>
        )
      )}
    </Box>
  ),
};

/** Buttons with trailing keyboard shortcuts, across variants and sizes. */
export const WithShortcuts: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" alignItems="flex-start">
      <Box display="flex" flexWrap="wrap" alignItems="center" gap="2">
        {buttonVariants.map((variant) => (
          <Button key={variant} variant={variant} kbd={<Kbd>K</Kbd>}>
            {variant[0].toUpperCase() + variant.slice(1)}
          </Button>
        ))}
      </Box>

      <Box display="flex" flexWrap="wrap" alignItems="center" gap="2">
        {buttonVariants.map((variant) => (
          <Button
            key={variant}
            variant={variant}
            size="xs"
            kbd={
              <KbdGroup>
                <Kbd>⌘</Kbd>
                <Kbd>K</Kbd>
              </KbdGroup>
            }
          >
            {variant[0].toUpperCase() + variant.slice(1)}
          </Button>
        ))}
      </Box>

      <Box display="flex" flexWrap="wrap" alignItems="center" gap="2">
        <Button
          variant="primary"
          kbd={
            <KbdGroup>
              <Kbd>⌘</Kbd>
              <Kbd>⇧</Kbd>
              <Kbd>P</Kbd>
            </KbdGroup>
          }
        >
          Command palette
        </Button>
        <Button
          variant="secondary"
          size="xs"
          kbd={
            <KbdGroup>
              <Kbd>⌘</Kbd>
              <Kbd>S</Kbd>
            </KbdGroup>
          }
        >
          Save
        </Button>
      </Box>
    </Box>
  ),
};
