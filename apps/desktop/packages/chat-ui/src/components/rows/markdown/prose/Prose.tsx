import { useCommands } from '@components/contexts/CommandsContext';
import { useStreamAnimation } from '@components/contexts/StreamContext';
import { useTheme } from '@components/contexts/ThemeContext';
import { BlockFrame } from '@components/engine/block-frame';
import {
  MentionAtIcon,
  MentionFileIcon,
  MentionIssueIcon,
  MentionSymbolIcon,
} from '@components/primitives/icons';
import type {
  BulletLayout,
  FragmentLayout,
  LineLayout,
  ProseLaidOut,
} from '@core/layout/layout-types';
import { mentionDisplayText } from '@core/markdown/document';
import type { InlineMention, InlineRun } from '@core/markdown/document';
import type { JSX } from 'solid-js';
import { For, Match, Show, Switch, createMemo, onMount } from 'solid-js';
import { streamWordDelayMs } from './stream-word-animation';
import {
  bulletColor,
  commandChip,
  inlineCodeChip,
  linkFragment,
  mentionChip,
  mentionChipByKind,
  mentionPlain,
  pbullet,
  pf,
  pfVariants,
  pline,
  pquoteRail,
  quoteRailBar,
} from './prose.css';
import { streamWord, streamWordDelay } from '@styles/effects.css';

// ── Fragment ──────────────────────────────────────────────────────────────────

function fragKey(run: InlineRun, variant: string): string {
  if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(variant)) return `pf--${variant}`;
  if (run.kind === 'code') return 'pf--inline-code';
  if (run.kind === 'mention') return 'pf--mention';
  if (run.kind === 'text') {
    if (run.bold && run.italic) return 'pf--bold-italic';
    if (run.bold) return 'pf--bold';
    if (run.italic) return 'pf--italic';
    if (run.href) return 'pf--link';
  }
  return 'pf--body';
}

function fragVisualClass(run: InlineRun, variant: string): string {
  if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(variant)) return '';
  if (run.kind === 'code') return inlineCodeChip;
  if (run.kind === 'mention') {
    const mention = run as InlineMention;
    // Slash-command chips use a dedicated style.
    if (mention.tone === 'command') return commandChip;
    // Resolved context mentions use per-kind background colors.
    // Plain/math mentions (no mentionKind) keep the rounded-full blue tint.
    if (mention.mentionKind) return mentionChipByKind[mention.mentionKind] ?? mentionChip;
    return mentionPlain;
  }
  if (run.kind === 'text' && run.href) return linkFragment;
  return '';
}

// ── Word-splitting for streaming animation ────────────────────────────────────

/**
 * Split a fragment's text into alternating word/space runs, preserving
 * `white-space: pre` semantics (no trimming, no merging of spaces).
 * Returns [text, isWord] pairs.
 */
function splitFragmentWords(text: string): Array<[string, boolean]> {
  const parts = text.split(/(\s+)/);
  const result: Array<[string, boolean]> = [];
  for (const p of parts) {
    if (p.length === 0) continue;
    result.push([p, /\S/.test(p)]);
  }
  return result;
}

// ── Fragment ──────────────────────────────────────────────────────────────────

function ProseFragment(props: {
  run: InlineRun;
  frag: FragmentLayout;
  variant: string;
  blockId: string;
  /** Absolute word index of the first word in this fragment (0-based). Set only when streaming. */
  wordOffset?: number;
  /** Total word count in the block. Set only when streaming. */
  totalWords?: number;
  /** Frontier: words already revealed on the previous render. Set only when streaming. */
  frontier?: number;
}) {
  const commands = useCommands();
  const chips = useTheme()().chips;
  const key = fragKey(props.run, props.variant);
  const moduleCls = [pf, pfVariants[key]].filter(Boolean).join(' ');
  const visualCls = fragVisualClass(props.run, props.variant);
  const cls = visualCls ? `${moduleCls} ${visualCls}` : moduleCls;

  if (props.run.kind === 'text' && props.run.href) {
    const href = props.run.href;
    const classification = () => commands().classifyLink?.(href);

    const handleClick = (e: MouseEvent) => {
      const result = classification();
      if (result?.kind === 'workspace-file') {
        e.preventDefault();
        commands().onOpenFile?.({
          path: result.path,
          itemId: props.blockId,
          source: 'prose-link',
        });
      }
      // else: browser follows the <a> normally (new tab via target="_blank")
    };

    // Links are not word-animated (href spans are not appended incrementally).
    return (
      <a
        class={cls}
        style={{ left: `${props.frag.x}px` }}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={handleClick}
      >
        {props.frag.text}
      </a>
    );
  }

  if (props.run.kind === 'mention' && (props.run as InlineMention).mentionKind) {
    const mention = props.run as InlineMention;
    // Mentions are not split; fade as a single unit when streaming.
    const isNew =
      props.wordOffset !== undefined &&
      props.frontier !== undefined &&
      props.wordOffset >= props.frontier;

    const handleMentionClick = () => {
      if (!mention.mentionKind) return;
      commands().onClickMention?.({
        id: mention.id ?? mention.label,
        label: mention.label,
        kind: mention.mentionKind,
        itemId: props.blockId,
        source: 'prose-mention',
      });
    };
    const isClickable = () => !!commands().onClickMention;

    return (
      <span
        classList={{ [cls]: true, [streamWord]: isNew }}
        onClick={handleMentionClick}
        style={
          {
            [streamWordDelay]: isNew
              ? `${streamWordDelayMs(props.wordOffset ?? 0, props.frontier ?? 0)}ms`
              : undefined,
            cursor: isClickable() ? 'pointer' : undefined,
            left: `${props.frag.x}px`,
            display: 'inline-flex',
            'align-items': 'center',
            gap: `${chips.mentionIconGap}px`,
          } as JSX.CSSProperties
        }
      >
        <span
          style={{
            display: 'flex',
            width: `${chips.mentionIconW}px`,
            height: `${chips.mentionIconW}px`,
            'flex-shrink': '0',
            'align-items': 'center',
            'justify-content': 'center',
            overflow: 'hidden',
          }}
        >
          <Show
            when={mention.iconUrl}
            fallback={
              <Show
                when={mention.iconClass}
                fallback={
                  <Switch fallback={<MentionAtIcon />}>
                    <Match when={mention.mentionKind === 'file'}>
                      <MentionFileIcon />
                    </Match>
                    <Match when={mention.mentionKind === 'issue'}>
                      <MentionIssueIcon />
                    </Match>
                    <Match when={mention.mentionKind === 'symbol'}>
                      <MentionSymbolIcon />
                    </Match>
                  </Switch>
                }
              >
                {(ic) => <i class={`${ic()} leading-none`} style={{ 'font-size': '11px' }} />}
              </Show>
            }
          >
            {(url) => (
              <img
                src={url()}
                alt=""
                style={{ width: '100%', height: '100%', 'object-fit': 'contain' }}
              />
            )}
          </Show>
        </span>
        <span>{mentionDisplayText(mention)}</span>
      </span>
    );
  }

  // Plain text (body / bold / italic / code chip / plain mention).
  // When streaming, split into per-word spans and animate the new tail.
  const isStreaming =
    props.wordOffset !== undefined &&
    props.frontier !== undefined &&
    props.totalWords !== undefined;

  if (isStreaming && props.run.kind === 'text' && !/^\s+$/.test(props.frag.text)) {
    const wordPairs = splitFragmentWords(props.frag.text);
    let localIdx = props.wordOffset!;
    return (
      <span class={cls} style={{ left: `${props.frag.x}px` }}>
        <For each={wordPairs}>
          {([chunk, isWord]) => {
            if (!isWord) return <>{chunk}</>;
            const idx = localIdx++;
            const isNew = idx >= props.frontier!;
            return isNew ? (
              <span
                class={streamWord}
                style={
                  {
                    [streamWordDelay]: `${streamWordDelayMs(idx, props.frontier!)}ms`,
                  } as JSX.CSSProperties
                }
              >
                {chunk}
              </span>
            ) : (
              <>{chunk}</>
            );
          }}
        </For>
      </span>
    );
  }

  return (
    <span class={cls} style={{ left: `${props.frag.x}px` }}>
      {props.frag.text}
    </span>
  );
}

// ── Line ──────────────────────────────────────────────────────────────────────

function ProseLine(props: {
  line: LineLayout;
  lineHeight: number;
  runs: InlineRun[];
  variant: string;
  blockId: string;
  /** Per-fragment word offsets. Present only when streaming. */
  fragWordOffsets?: number[];
  totalWords?: number;
  frontier?: number;
}) {
  return (
    <div
      class={pline}
      style={{
        top: `${props.line.top}px`,
        left: `${props.line.left}px`,
        height: `${props.lineHeight}px`,
      }}
    >
      <For each={props.line.fragments}>
        {(frag, i) => {
          const run = props.runs[frag.runIndex];
          return run ? (
            <ProseFragment
              run={run}
              frag={frag}
              variant={props.variant}
              blockId={props.blockId}
              wordOffset={props.fragWordOffsets?.[i()]}
              totalWords={props.totalWords}
              frontier={props.frontier}
            />
          ) : null;
        }}
      </For>
    </div>
  );
}

// ── Bullet & QuoteRail ────────────────────────────────────────────────────────

function ProseBullet(props: { bullet: BulletLayout }) {
  return (
    <span
      class={`${pbullet} ${bulletColor}`}
      style={{ left: `${props.bullet.x}px`, top: `${props.bullet.top}px` }}
      aria-hidden="true"
    >
      {props.bullet.char}
    </span>
  );
}

function ProseQuoteRail(props: { left: number }) {
  return <div class={`${pquoteRail} ${quoteRailBar}`} style={{ left: `${props.left}px` }} />;
}

// ── Main component ────────────────────────────────────────────────────────────

export type ProseProps = {
  block: ProseLaidOut;
  runs: InlineRun[];
  variant: string;
};

export function Prose(props: ProseProps) {
  const streamAnim = useStreamAnimation();

  // Pre-compute per-fragment word offsets, the block total, and a per-line
  // base-flat index so that ProseFragment can determine whether each word is
  // new without scanning the whole block. Rebuilt whenever lines/runs change
  // (i.e. each streaming tick).
  //
  // lineBaseFlat[i] = total fragment count across lines 0…i-1, so a fragment
  // at (lineIdx, fragIdx) maps to fragWordOffsets[lineBaseFlat[lineIdx] + fragIdx]
  // in O(1) rather than summing per-line counts on every access (was O(lines^2)).
  const fragData = createMemo<{
    fragWordOffsets: number[];
    lineBaseFlat: number[];
    totalWords: number;
    frontier: number;
  } | null>(() => {
    if (!streamAnim) return null;

    const offsets: number[] = [];
    const lineBaseFlat: number[] = [];
    let cursor = 0;

    for (const line of props.block.lines) {
      lineBaseFlat.push(offsets.length);
      for (const frag of line.fragments) {
        offsets.push(cursor);
        const run = props.runs[frag.runIndex];
        if (run && run.kind === 'text' && !/^\s+$/.test(frag.text)) {
          // Count only non-space words (matching splitFragmentWords logic).
          const words = frag.text.split(/\s+/).filter((w) => w.length > 0);
          cursor += words.length;
        } else if (run && run.kind !== 'text') {
          // Non-text runs (code chip, mention) count as 1 unit.
          cursor += 1;
        }
        // Pure-whitespace fragments and breaks contribute 0.
      }
    }

    return {
      fragWordOffsets: offsets,
      lineBaseFlat,
      totalWords: cursor,
      frontier: streamAnim.frontier.get(props.block.id) ?? 0,
    };
  });

  // After rendering, advance the frontier so the next chunk only animates
  // words appended after this render.
  onMount(() => {
    if (!streamAnim) return;
    const d = fragData();
    if (d) streamAnim.frontier.set(props.block.id, d.totalWords);
  });

  return (
    <BlockFrame layout={props.block}>
      <Show when={props.block.quoteRail}>
        <ProseQuoteRail left={(props.block.lines[0]?.left ?? 18) - 10} />
      </Show>
      <Show when={props.block.bullet}>{(bullet) => <ProseBullet bullet={bullet()} />}</Show>
      <For each={props.block.lines}>
        {(line, lineIdx) => {
          const d = fragData();
          // Build per-fragment offset array for this line using O(1) prefix lookup.
          const lineFragOffsets = d
            ? line.fragments.map((_, fi) => d.fragWordOffsets[d.lineBaseFlat[lineIdx()] + fi] ?? 0)
            : undefined;
          return (
            <ProseLine
              line={line}
              lineHeight={props.block.lineHeight}
              runs={props.runs}
              variant={props.variant}
              blockId={props.block.id}
              fragWordOffsets={lineFragOffsets}
              totalWords={d?.totalWords}
              frontier={d?.frontier}
            />
          );
        }}
      </For>
    </BlockFrame>
  );
}
