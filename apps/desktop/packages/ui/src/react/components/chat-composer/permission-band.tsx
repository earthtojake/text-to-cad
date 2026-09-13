/**
 * PermissionBand — a composer-docked band that surfaces an ACP permission
 * request to the user.
 *
 * Renders flush above the composer input box, styled like NoticeBand but with
 * a SplitButton instead of a dismiss button.  A "1 of N" counter is shown when
 * multiple requests are queued, so the user knows more are coming.
 *
 * Tone mapping from ACP PermissionOption.kind:
 *   allow_*  → accept
 *   reject_* → reject
 *   other    → neutral
 */

import { cx } from '@styles/utilities/cx';
import { ShieldAlertIcon } from 'lucide-react';
import * as React from 'react';
import { Button } from '@/react/primitives/button';
import { SplitButton, type SplitButtonOption } from '@/react/primitives/split-button';
import { composerThemeScope } from './composer-contract.css';
import * as styles from './permission-band.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export type ComposerPermissionOption = {
  optionId: string;
  name: string;
  kind: string;
  /** Secondary text shown under the option in the menu. */
  description?: string;
};

export type ComposerPermissionRequest = {
  requestId: string;
  /** 'permission' asks whether the agent may act; 'question' is the agent asking the user. */
  kind?: 'permission' | 'question';
  /** Pre-formatted action verb, e.g. "Read a File", "Execute". */
  title: string;
  /** What is being asked or granted: a plan, a command, file paths, the question text. */
  body?: string;
  options: ComposerPermissionOption[];
};

export interface PermissionBandProps {
  request: ComposerPermissionRequest;
  /** Total pending count including this one. Used to render "1 of N". */
  queueCount?: number;
  /** Called with the chosen optionId. Rejection is represented by reject_* options. */
  onResolve: (optionId: string) => void;
  className?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const MAX_INLINE_QUESTION_OPTIONS = 3;

/** The Button primitive speaks in outcome tones; map the option kinds onto them. */
function kindToButtonTone(kind: string): 'success' | 'destructive' | undefined {
  if (kind.startsWith('allow_') || kind === 'answer') return 'success';
  if (kind.startsWith('reject_')) return 'destructive';
  return undefined;
}

function kindToTone(kind: string): SplitButtonOption['tone'] {
  if (kind.startsWith('allow_') || kind === 'answer') return 'accept';
  if (kind.startsWith('reject_')) return 'reject';
  return 'neutral';
}

function defaultSelectedId(options: ComposerPermissionOption[]): string | undefined {
  return (
    options.find((o) => o.kind === 'allow_once')?.optionId ??
    options.find((o) => o.kind.startsWith('allow_') || o.kind === 'answer')?.optionId ??
    options[0]?.optionId
  );
}

// ── PermissionBand ────────────────────────────────────────────────────────────

export function PermissionBand({
  request,
  queueCount = 1,
  onResolve,
  className,
}: PermissionBandProps) {
  const isQuestion = request.kind === 'question';
  // A short question reads best with every answer visible; permissions and long
  // option lists keep the split button so the primary choice stays one click away.
  const showEveryOption = isQuestion && request.options.length <= MAX_INLINE_QUESTION_OPTIONS;
  const splitOptions: SplitButtonOption[] = request.options.map((o) => ({
    id: o.optionId,
    label: o.name,
    ...(o.description ? { description: o.description } : {}),
    tone: kindToTone(o.kind),
  }));

  const [selectedId, setSelectedId] = React.useState<string | undefined>(() =>
    defaultSelectedId(request.options)
  );

  // Reset selection when the request changes (a new request came in after resolving).
  // request.options is intentionally excluded: we only want to reset on a new request (new requestId),
  // not every time the options array reference changes while the same request is displayed.
  React.useEffect(() => {
    setSelectedId(defaultSelectedId(request.options));
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [request.requestId]);

  return (
    <div className={cx(styles.band, className)}>
      <ShieldAlertIcon className={styles.bandIcon} aria-hidden />

      {/* Context label */}
      <span className={styles.bandLabel}>
        <span className={styles.bandLabelStrong}>{isQuestion ? 'Question' : 'Allow'}</span>{' '}
        <span>{request.title}</span>
        {queueCount > 1 && (
          <span className={styles.bandCounter}>
            ({1} of {queueCount})
          </span>
        )}
        {request.body && (
          <span className={styles.bandBody} title={request.body}>
            {request.body}
          </span>
        )}
      </span>

      {showEveryOption ? (
        <span className={styles.bandActions}>
          {request.options.map((option) => (
            <Button
              key={option.optionId}
              size="xs"
              variant="secondary"
              tone={kindToButtonTone(option.kind)}
              title={option.description}
              onClick={() => onResolve(option.optionId)}
            >
              {option.name}
            </Button>
          ))}
        </span>
      ) : (
        /* Split button — its option menu portals out of the composer root and
           must carry the theme-bridge scope. */
        <SplitButton
          options={splitOptions}
          selectedId={selectedId}
          onSelectedChange={setSelectedId}
          onAction={onResolve}
          size="xs"
          variant="secondary"
          className={styles.bandAction}
          menuClassName={composerThemeScope}
        />
      )}
    </div>
  );
}
