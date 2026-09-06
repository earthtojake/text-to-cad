import { cx } from '@styles/utilities/cx';
import { ExpandIcon } from 'lucide-react';
import * as React from 'react';
import { Button } from '@/react/primitives/button';
import { Tooltip } from '@/react/primitives/tooltip';
import { ZoomViewerDialog } from '../image-viewer/zoom-viewer-dialog';
import { renderMermaid } from './mermaid';
import * as styles from './markdown.css';

const GENERIC_RENDER_ERROR = 'Unable to render Mermaid diagram.';

export interface MermaidBlockProps {
  /** Mermaid diagram source text. */
  source: string;
  /** Denser paddings for the compact Markdown variant. */
  compact?: boolean;
}

/**
 * Renders a Mermaid code fence as an inline SVG preview with a hover-revealed
 * expand affordance (also keyboard-expandable via Enter/Space) that opens the
 * pan/zoom viewer dialog. Rendering is synchronous via beautiful-mermaid with
 * CSS-var theming, so the SVG adapts to theme flips without re-rendering.
 */
export function MermaidBlock({ source, compact }: MermaidBlockProps) {
  const result = React.useMemo(() => renderMermaid(source), [source]);
  const [isExpanded, setIsExpanded] = React.useState(false);

  if (result.kind === 'error') {
    return (
      <div className={cx(styles.mermaidError, compact && styles.mermaidErrorCompact)} role="alert">
        <div className={styles.mermaidErrorTitle}>{GENERIC_RENDER_ERROR}</div>
        {result.message && result.message !== GENERIC_RENDER_ERROR && (
          <div className={styles.mermaidErrorMessage}>{result.message}</div>
        )}
        <pre className={styles.mermaidErrorSource}>
          <code>{source}</code>
        </pre>
      </div>
    );
  }

  const expandFromInteraction = (event: React.SyntheticEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsExpanded(true);
  };

  const handlePreviewKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      expandFromInteraction(event);
    }
  };

  return (
    <div className={styles.mermaidPreviewContainer}>
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon
              aria-label="Expand Mermaid diagram"
              className={styles.mermaidExpandButton}
              onClick={expandFromInteraction}
            >
              <ExpandIcon style={{ width: '0.75rem', height: '0.75rem' }} />
            </Button>
          }
        />
        <Tooltip.Content side="left" align="end">
          Expand diagram
        </Tooltip.Content>
      </Tooltip.Root>
      <div
        role="button"
        tabIndex={0}
        aria-label="Expand Mermaid diagram preview"
        className={cx(styles.mermaidPreview, compact && styles.mermaidPreviewCompact)}
        onClick={expandFromInteraction}
        onKeyDown={handlePreviewKeyDown}
        dangerouslySetInnerHTML={{ __html: result.svg }}
      />
      <ZoomViewerDialog
        open={isExpanded}
        onOpenChange={setIsExpanded}
        ariaLabel="Mermaid diagram"
        contentKey={source}
      >
        <div
          className={styles.mermaidDialogContent}
          dangerouslySetInnerHTML={{ __html: result.svg }}
        />
      </ZoomViewerDialog>
    </div>
  );
}
