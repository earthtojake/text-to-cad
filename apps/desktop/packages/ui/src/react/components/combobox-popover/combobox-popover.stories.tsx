import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { Bot, Cpu, Plus, Settings, Zap } from 'lucide-react';
import { useState } from 'react';
import { Box } from '@/react/primitives/box';
import { ComboboxPopover } from '.';
import * as s from '@react/story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  description: string;
  contextK: number;
  speed: number;
  intelligence: number;
}

const MODELS: ModelItem[] = [
  {
    id: 'claude-opus-4',
    name: 'Claude Opus 4',
    provider: 'Anthropic',
    description: 'Most capable model for complex reasoning and nuanced tasks.',
    contextK: 200,
    speed: 0.4,
    intelligence: 1.0,
  },
  {
    id: 'claude-sonnet-4-5',
    name: 'Claude Sonnet 4.5',
    provider: 'Anthropic',
    description: 'Excellent balance of speed and intelligence.',
    contextK: 200,
    speed: 0.75,
    intelligence: 0.85,
  },
  {
    id: 'claude-haiku-4',
    name: 'Claude Haiku 4',
    provider: 'Anthropic',
    description: 'Fast and efficient for high-volume tasks.',
    contextK: 200,
    speed: 0.95,
    intelligence: 0.65,
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    provider: 'OpenAI',
    description: 'OpenAI flagship multimodal model.',
    contextK: 128,
    speed: 0.7,
    intelligence: 0.9,
  },
  {
    id: 'gpt-4o-mini',
    name: 'GPT-4o Mini',
    provider: 'OpenAI',
    description: 'Lightweight, cost-efficient GPT-4o variant.',
    contextK: 128,
    speed: 0.9,
    intelligence: 0.7,
  },
  {
    id: 'gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    provider: 'Google',
    description: "Google's most capable model — 1M context window.",
    contextK: 1000,
    speed: 0.6,
    intelligence: 0.95,
  },
];

function BarMeter({ value }: { value: number }) {
  const filled = Math.round(Math.max(0, Math.min(1, value)) * 5);
  return (
    <Box display="flex" alignItems="center" gap="0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={cx(sx({ rounded: 'full' }), s.size15)}
          style={{ background: i < filled ? 'var(--em-foreground-muted)' : 'var(--em-border)' }}
        />
      ))}
    </Box>
  );
}

function ModelDetailCard({ item }: { item: ModelItem }) {
  return (
    <Box padding="3" fontSize="sm" className={s.w52} style={{ color: 'var(--em-foreground)' }}>
      <Box display="flex" alignItems="center" gap="1.5">
        <Bot
          className={cx(s.size4, sx({ flexShrink: 0 }))}
          style={{ color: 'var(--em-foreground-muted)' }}
        />
        <p className={cx(sx({ lineHeight: 'tight' }))}>{item.name}</p>
      </Box>
      <p
        className={cx(sx({ marginTop: '1.5', fontSize: 'xs', lineHeight: 'snug' }))}
        style={{ color: 'var(--em-foreground-muted)' }}
      >
        {item.description}
      </p>
      <Box
        marginTop="2"
        borderTopWidth="1"
        borderStyle="solid"
        paddingTop="2"
        className={s.spaceY15}
        style={{ borderColor: 'var(--em-border)' }}
      >
        <Box display="flex" alignItems="center" justifyContent="space-between" fontSize="xs">
          <span style={{ color: 'var(--em-foreground-muted)' }}>Context</span>
          <span style={{ color: 'var(--em-foreground)' }}>{item.contextK}K</span>
        </Box>
        <Box display="flex" alignItems="center" justifyContent="space-between" fontSize="xs">
          <span
            className={cx(sx({ display: 'flex', alignItems: 'center', gap: '1' }))}
            style={{ color: 'var(--em-foreground-muted)' }}
          >
            <Zap className={s.size3} /> Speed
          </span>
          <BarMeter value={item.speed} />
        </Box>
        <Box display="flex" alignItems="center" justifyContent="space-between" fontSize="xs">
          <span
            className={cx(sx({ display: 'flex', alignItems: 'center', gap: '1' }))}
            style={{ color: 'var(--em-foreground-muted)' }}
          >
            <Cpu className={s.size3} /> Intelligence
          </span>
          <BarMeter value={item.intelligence} />
        </Box>
      </Box>
    </Box>
  );
}

const meta: Meta = {
  title: 'Components/ComboboxPopover',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

function BasicStory() {
  const [value, setValue] = useState<string>('claude-sonnet-4-5');
  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap="4">
      <p className={cx(sx({ fontSize: 'xs' }))} style={{ color: 'var(--em-foreground-muted)' }}>
        Selected: <strong>{MODELS.find((m) => m.id === value)?.name ?? '—'}</strong>
      </p>
      <ComboboxPopover<ModelItem>
        items={MODELS}
        value={value}
        onValueChange={setValue}
        itemToKey={(m) => m.id}
        itemToLabel={(m) => m.name}
        searchPlaceholder="Search models…"
        renderTrigger={(selected) => (
          <span className={cx(sx({ fontSize: 'xs' }))}>{selected?.name ?? 'Pick a model'}</span>
        )}
        renderItem={(item) => (
          <span className={cx(sx({ flex: '1', fontSize: 'sm' }), 'truncate')}>{item.name}</span>
        )}
      />
    </Box>
  );
}

function WithDetailHoverCardStory() {
  const [value, setValue] = useState<string>('claude-sonnet-4-5');
  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap="4">
      <p className={cx(sx({ fontSize: 'xs' }))} style={{ color: 'var(--em-foreground-muted)' }}>
        Hover any row in the list to see the detail card.
      </p>
      <ComboboxPopover<ModelItem>
        items={MODELS}
        value={value}
        onValueChange={setValue}
        itemToKey={(m) => m.id}
        itemToLabel={(m) => m.name}
        searchPlaceholder="Search models…"
        renderTrigger={(selected) => (
          <span className={cx(sx({ fontSize: 'xs' }))}>{selected?.name ?? 'Pick a model'}</span>
        )}
        renderItem={(item) => (
          <span className={cx(sx({ flex: '1', fontSize: 'sm' }), 'truncate')}>{item.name}</span>
        )}
        renderItemDetail={(item) => <ModelDetailCard item={item} />}
        detailSide="right"
        detailAlign="start"
      />
    </Box>
  );
}

function DetailCardAboveStory() {
  const [value, setValue] = useState<string>('gpt-4o');
  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap="4">
      <p className={cx(sx({ fontSize: 'xs' }))} style={{ color: 'var(--em-foreground-muted)' }}>
        Hover a row — detail card appears above the popover (for bottom-anchored selectors like the
        composer toolbar).
      </p>
      <ComboboxPopover<ModelItem>
        items={MODELS}
        value={value}
        onValueChange={setValue}
        itemToKey={(m) => m.id}
        itemToLabel={(m) => m.name}
        searchPlaceholder="Search models…"
        renderTrigger={(selected) => (
          <span className={cx(sx({ fontSize: 'xs' }))}>{selected?.name ?? 'Pick a model'}</span>
        )}
        renderItem={(item) => (
          <Box display="flex" alignItems="center" gap="2">
            <Bot
              className={cx(s.size35, sx({ flexShrink: 0 }))}
              style={{ color: 'var(--em-foreground-muted)' }}
            />
            <span className={cx(sx({ flex: '1', fontSize: 'sm' }), 'truncate')}>{item.name}</span>
            <span
              className={cx(sx({ fontSize: 'xs' }))}
              style={{ color: 'var(--em-foreground-muted)' }}
            >
              {item.provider}
            </span>
          </Box>
        )}
        renderItemDetail={(item) => <ModelDetailCard item={item} />}
        detailSide="top"
        detailAlign="start"
      />
    </Box>
  );
}

function WithFooterStory() {
  const [value, setValue] = useState<string>('claude-sonnet-4-5');
  const [lastAction, setLastAction] = useState<string>('—');
  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap="4">
      <p className={cx(sx({ fontSize: 'xs' }))} style={{ color: 'var(--em-foreground-muted)' }}>
        Selected: <strong>{MODELS.find((m) => m.id === value)?.name ?? '—'}</strong>
        {' · '}
        Last action: <strong>{lastAction}</strong>
      </p>
      <p className={cx(sx({ fontSize: 'xs' }))} style={{ color: 'var(--em-foreground-muted)' }}>
        Type in the search box — footer actions stay visible while filtering.
      </p>
      <ComboboxPopover<ModelItem>
        items={MODELS}
        value={value}
        onValueChange={setValue}
        itemToKey={(m) => m.id}
        itemToLabel={(m) => m.name}
        searchPlaceholder="Search models…"
        renderTrigger={(selected) => (
          <span className={cx(sx({ fontSize: 'xs' }))}>{selected?.name ?? 'Pick a model'}</span>
        )}
        renderItem={(item) => (
          <span className={cx(sx({ flex: '1', fontSize: 'sm' }), 'truncate')}>{item.name}</span>
        )}
        renderFooter={() => (
          <Box display="flex" flexDirection="column" padding="1" gap="0.5">
            <button
              type="button"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                width: '100%',
                padding: '0.375rem 0.5rem',
                borderRadius: 'var(--em-radius-sm)',
                fontSize: 'var(--em-text-sm)',
                color: 'var(--em-foreground-muted)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  'var(--em-surface-hover)';
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--em-foreground)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor = '';
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--em-foreground-muted)';
              }}
              onClick={() => setLastAction('Add model clicked')}
            >
              <Plus style={{ width: '1rem', height: '1rem', flexShrink: 0 }} />
              Add model
            </button>
            <button
              type="button"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                width: '100%',
                padding: '0.375rem 0.5rem',
                borderRadius: 'var(--em-radius-sm)',
                fontSize: 'var(--em-text-sm)',
                color: 'var(--em-foreground-muted)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  'var(--em-surface-hover)';
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--em-foreground)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor = '';
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--em-foreground-muted)';
              }}
              onClick={() => setLastAction('Manage providers clicked')}
            >
              <Settings style={{ width: '1rem', height: '1rem', flexShrink: 0 }} />
              Manage providers
            </button>
          </Box>
        )}
      />
    </Box>
  );
}

export const Basic: Story = {
  name: 'Basic',
  render: () => <BasicStory />,
};

export const WithDetailHoverCard: Story = {
  name: 'With detail hover card',
  render: () => <WithDetailHoverCardStory />,
};

export const DetailCardAbove: Story = {
  name: 'Detail card above (detailSide=top)',
  render: () => <DetailCardAboveStory />,
};

export const WithFooter: Story = {
  name: 'With footer actions',
  render: () => <WithFooterStory />,
};

export const ContentAtLeastTriggerWidth: Story = {
  render: () => (
    <ComboboxPopover<ModelItem>
      items={MODELS}
      value="gpt-4o"
      onValueChange={() => {}}
      onOpenChange={() => {}}
      itemToKey={(model) => model.id}
      itemToLabel={(model) => model.name}
      renderTrigger={(selected) => selected?.name ?? 'Pick a model'}
      renderItem={(model) => model.name}
      contentWidth="content-at-least-trigger"
    />
  ),
};
