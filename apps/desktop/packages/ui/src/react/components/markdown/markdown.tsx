import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import ReactMarkdown from 'react-markdown';
import type { ExtraProps, Options as ReactMarkdownOptions } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { ExpandableImage } from '../image-viewer/expandable-image';
import { useHighlightedCode } from './highlight';
import { normalizeLatexDelimiters } from './markdown-latex';
import { MermaidBlock } from './mermaid-block';
import { sanitizeSchema } from './sanitize-schema';
import * as styles from './markdown.css';

export type MarkdownVariant = 'full' | 'compact';

export interface MarkdownProps {
  content: string;
  /** `full` renders document-scale typography; `compact` is denser for previews. */
  variant?: MarkdownVariant;
  className?: string;
  /**
   * Allow embedded HTML in the source (rehype-raw). Defaults to on for the
   * `full` variant only; all HTML passes through the sanitize schema.
   */
  allowHtml?: boolean;
  /**
   * Link-opening injection point. Called on anchor click with the href; return
   * true to claim the click (default navigation is prevented). Hosts should
   * route external links through their open-external flow here — unhandled
   * links fall back to the anchor's target="_blank" behavior.
   */
  onOpenLink?: (href: string) => boolean | void;
  /**
   * Optional callback for resolving non-external image src values (e.g.
   * relative paths inside a workspace). Should return a `data:` URI string, or
   * `null` to render a "not found" placeholder. When omitted, local images are
   * not resolved.
   */
  resolveImage?: (src: string) => Promise<string | null>;
}

type RehypePlugins = NonNullable<ReactMarkdownOptions['rehypePlugins']>;
type RemarkPlugins = NonNullable<ReactMarkdownOptions['remarkPlugins']>;
type Components = NonNullable<ReactMarkdownOptions['components']>;

const REMARK_PLUGINS: RemarkPlugins = [remarkGfm, remarkMath];
// Sanitize must run before rehype-katex: user input is sanitized while KaTeX's
// trusted output passes through untouched (see sanitize-schema.ts).
const FULL_REHYPE_PLUGINS: RehypePlugins = [
  rehypeRaw,
  [rehypeSanitize, sanitizeSchema],
  rehypeKatex,
];
const COMPACT_REHYPE_PLUGINS: RehypePlugins = [[rehypeSanitize, sanitizeSchema], rehypeKatex];

// ── Images ────────────────────────────────────────────────────────────────────

/** Resolves a local image src via the provided callback and renders as a base64 data URI. */
function ResolvedImage({
  src,
  alt,
  resolveImage,
  containerClassName,
  imageClassName,
}: {
  src: string;
  alt: string;
  resolveImage: (src: string) => Promise<string | null>;
  containerClassName: string;
  imageClassName: string;
}) {
  const [dataUrl, setDataUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    resolveImage(src)
      .then((result) => {
        if (cancelled) return;
        if (result) {
          setDataUrl(result);
        } else {
          setError(true);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [src, resolveImage]);

  if (error) {
    return <span className={styles.imagePlaceholder}>[Image not found: {src}]</span>;
  }
  if (!dataUrl) {
    return <span className={styles.imagePlaceholder}>Loading image...</span>;
  }
  return (
    <ExpandableImage
      src={dataUrl}
      alt={alt}
      containerClassName={containerClassName}
      className={imageClassName}
    />
  );
}

// ── Code blocks ───────────────────────────────────────────────────────────────

function getCodeBlock(children: React.ReactNode, className?: string) {
  const language = /language-(\w+)/.exec(className || '')?.[1] ?? '';
  const isBlock = className?.includes('language-') ?? false;
  const code = String(children).replace(/\n$/, '');
  return { code, isBlock, language };
}

/** Shiki-highlighted block code; renders plain text while the grammar loads. */
function HighlightedCode({ code, language }: { code: string; language: string }) {
  const lines = useHighlightedCode(code, language);
  return (
    <code className={styles.codeBlockFull}>
      {lines
        ? lines.map((line, lineIndex) => (
            <span key={lineIndex}>
              {line.map((token, tokenIndex) => (
                <span key={tokenIndex} style={token.color ? { color: token.color } : undefined}>
                  {token.content}
                </span>
              ))}
              {'\n'}
            </span>
          ))
        : code}
    </code>
  );
}

function renderMermaidCodeBlock(
  children: React.ReactNode,
  className: string | undefined,
  compact?: boolean
) {
  const { code, isBlock, language } = getCodeBlock(children, className);
  if (!isBlock || language !== 'mermaid') return null;
  return <MermaidBlock source={code} compact={compact} />;
}

function isOnlyMermaidBlockChild(children: React.ReactNode): boolean {
  const child = Array.isArray(children) ? children[0] : children;
  return React.isValidElement(child) && child.type === MermaidBlock;
}

// ── Component maps ────────────────────────────────────────────────────────────

type WithChildren = { children?: React.ReactNode };
type WithChildrenAndClass = { children?: React.ReactNode; className?: string };
type AnchorProps = { href?: string; children?: React.ReactNode };
type ImgProps = React.ComponentPropsWithoutRef<'img'> & ExtraProps;

function handleAnchorClick(
  href: string | undefined,
  onOpenLink: MarkdownProps['onOpenLink'],
  event: React.MouseEvent
) {
  if (!href) return;
  if (onOpenLink?.(href)) {
    event.preventDefault();
  }
}

function useFullComponents(
  resolveImage?: MarkdownProps['resolveImage'],
  onOpenLink?: MarkdownProps['onOpenLink']
): Components {
  return React.useMemo(
    () => ({
      h1: ({ children }: WithChildren) => <h1 className={styles.h1Full}>{children}</h1>,
      h2: ({ children }: WithChildren) => <h2 className={styles.h2Full}>{children}</h2>,
      h3: ({ children }: WithChildren) => <h3 className={styles.h3Full}>{children}</h3>,
      h4: ({ children }: WithChildren) => <h4 className={styles.h4Full}>{children}</h4>,
      h5: ({ children }: WithChildren) => <h5 className={styles.h5Full}>{children}</h5>,
      h6: ({ children }: WithChildren) => <h6 className={styles.h6Full}>{children}</h6>,
      p: ({ children }: WithChildren) => <p className={styles.paragraphFull}>{children}</p>,
      ul: ({ children }: WithChildren) => <ul className={styles.unorderedListFull}>{children}</ul>,
      ol: ({ children }: WithChildren) => <ol className={styles.orderedListFull}>{children}</ol>,
      li: ({ children }: WithChildren) => <li className={styles.listItem}>{children}</li>,
      code: ({ children, className }: WithChildrenAndClass) => {
        const mermaidBlock = renderMermaidCodeBlock(children, className);
        if (mermaidBlock) return mermaidBlock;

        const { code, isBlock, language } = getCodeBlock(children, className);
        if (isBlock) {
          return <HighlightedCode code={code} language={language} />;
        }
        return <code className={styles.inlineCodeFull}>{children}</code>;
      },
      pre: ({ children }: WithChildren) =>
        isOnlyMermaidBlockChild(children) ? (
          <>{children}</>
        ) : (
          <pre className={styles.preFull}>{children}</pre>
        ),
      a: ({ href, children }: AnchorProps) => (
        <a
          href={href}
          className={styles.link}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(event) => handleAnchorClick(href, onOpenLink, event)}
        >
          {children}
        </a>
      ),
      blockquote: ({ children }: WithChildren) => (
        <blockquote className={styles.blockquoteFull}>{children}</blockquote>
      ),
      table: ({ children }: WithChildren) => (
        <div className={styles.tableWrapperFull}>
          <table className={styles.tableFull}>{children}</table>
        </div>
      ),
      thead: ({ children }: WithChildren) => (
        <thead className={styles.tableHeadFull}>{children}</thead>
      ),
      th: ({ children }: WithChildren) => (
        <th className={styles.tableHeaderCellFull}>{children}</th>
      ),
      td: ({ children }: WithChildren) => <td className={styles.tableCellFull}>{children}</td>,
      hr: () => <hr className={styles.dividerFull} />,
      img: ({ node: _node, src, alt, className, ...props }: ImgProps) => {
        const isExternal = typeof src === 'string' && /^https?:\/\//i.test(src);
        if (!isExternal && resolveImage && src) {
          return (
            <ResolvedImage
              src={src}
              alt={alt || ''}
              resolveImage={resolveImage}
              containerClassName={styles.imageContainerFull}
              imageClassName={styles.imageFull}
            />
          );
        }
        return (
          <ExpandableImage
            src={src}
            alt={alt || ''}
            containerClassName={styles.imageContainerFull}
            className={cx(styles.imageFull, className)}
            {...props}
          />
        );
      },
      strong: ({ children }: WithChildren) => <strong className={styles.strong}>{children}</strong>,
      input: ({
        checked,
        disabled: _disabled,
        ...props
      }: React.ComponentPropsWithoutRef<'input'>) => (
        <input
          type="checkbox"
          checked={checked}
          readOnly
          aria-disabled="true"
          tabIndex={-1}
          className={styles.taskCheckbox}
          {...props}
        />
      ),
    }),
    [resolveImage, onOpenLink]
  );
}

function useCompactComponents(onOpenLink?: MarkdownProps['onOpenLink']): Components {
  return React.useMemo(
    () => ({
      h1: ({ children }: WithChildren) => <h2 className={styles.h1Compact}>{children}</h2>,
      h2: ({ children }: WithChildren) => <h3 className={styles.h1Compact}>{children}</h3>,
      h3: ({ children }: WithChildren) => <h4 className={styles.h3Compact}>{children}</h4>,
      p: ({ children }: WithChildren) => <p className={styles.paragraphCompact}>{children}</p>,
      ul: ({ children }: WithChildren) => (
        <ul className={styles.unorderedListCompact}>{children}</ul>
      ),
      ol: ({ children }: WithChildren) => <ol className={styles.orderedListCompact}>{children}</ol>,
      li: ({ children }: WithChildren) => <li className={styles.listItem}>{children}</li>,
      code: ({ children, className }: WithChildrenAndClass) => {
        const mermaidBlock = renderMermaidCodeBlock(children, className, true);
        if (mermaidBlock) return mermaidBlock;

        const { isBlock } = getCodeBlock(children, className);
        if (isBlock) {
          return <code className={styles.codeBlockCompact}>{children}</code>;
        }
        return <code className={styles.inlineCodeCompact}>{children}</code>;
      },
      pre: ({ children }: WithChildren) =>
        isOnlyMermaidBlockChild(children) ? (
          <>{children}</>
        ) : (
          <pre className={styles.preCompact}>{children}</pre>
        ),
      blockquote: ({ children }: WithChildren) => (
        <blockquote className={styles.blockquoteCompact}>{children}</blockquote>
      ),
      table: ({ children }: WithChildren) => (
        <div className={styles.tableWrapperCompact}>
          <table className={styles.tableCompact}>{children}</table>
        </div>
      ),
      thead: ({ children }: WithChildren) => (
        <thead className={styles.tableHeadCompact}>{children}</thead>
      ),
      th: ({ children }: WithChildren) => (
        <th className={styles.tableHeaderCellCompact}>{children}</th>
      ),
      td: ({ children }: WithChildren) => <td className={styles.tableCellCompact}>{children}</td>,
      hr: () => <hr className={styles.dividerCompact} />,
      strong: ({ children }: WithChildren) => <strong className={styles.strong}>{children}</strong>,
      a: ({ href, children }: AnchorProps) => (
        <a
          href={href}
          className={styles.linkCompact}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(event) => handleAnchorClick(href, onOpenLink, event)}
        >
          {children}
        </a>
      ),
      img: ({ node: _node, src, alt, className, ...props }: ImgProps) => (
        <ExpandableImage
          src={src}
          alt={alt || ''}
          containerClassName={styles.imageContainerCompact}
          className={cx(styles.imageCompact, className)}
          {...props}
        />
      ),
    }),
    [onOpenLink]
  );
}

// ── Markdown ──────────────────────────────────────────────────────────────────

/**
 * General-purpose markdown renderer: GFM + math (KaTeX) + sanitized HTML +
 * shiki code highlighting + Mermaid diagrams + expandable images.
 *
 * Math rendering requires `katex/dist/katex.min.css` to be loaded by the host.
 */
export function Markdown({
  content,
  variant = 'full',
  className,
  allowHtml = variant === 'full',
  resolveImage,
  onOpenLink,
}: MarkdownProps) {
  const fullComponents = useFullComponents(resolveImage, onOpenLink);
  const compactComponents = useCompactComponents(onOpenLink);

  const components = variant === 'full' ? fullComponents : compactComponents;
  const rehypePlugins = allowHtml ? FULL_REHYPE_PLUGINS : COMPACT_REHYPE_PLUGINS;
  const normalizedContent = React.useMemo(() => normalizeLatexDelimiters(content), [content]);

  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
