import { Button, Dialog, Tooltip } from '@emdash/ui/react/primitives';
import { Check, Copy, ExternalLink, Globe } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { defineModal } from '@core/primitives/modals/react';

export type ExternalLinkChoice = 'emdash-browser' | 'external-browser';

export type ExternalLinkChoiceDialogArgs = {
  url: string;
  canOpenInEmdashBrowser: boolean;
  onCopy: () => boolean | Promise<boolean>;
};

export function ExternalLinkChoiceDialog({
  url,
  canOpenInEmdashBrowser,
  onCopy,
}: ExternalLinkChoiceDialogArgs) {
  const controller = useModalController('confirmExternalLinkModal');
  const [copied, setCopied] = useState(false);
  const copyResetRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (copyResetRef.current !== null) window.clearTimeout(copyResetRef.current);
    },
    []
  );

  const handleCopy = async () => {
    if (!(await onCopy())) return;
    setCopied(true);
    if (copyResetRef.current !== null) window.clearTimeout(copyResetRef.current);
    copyResetRef.current = window.setTimeout(() => {
      setCopied(false);
      copyResetRef.current = null;
    }, 1_500);
  };

  return (
    <>
      <Dialog.Header showCloseButton={false}>
        <Dialog.Title>Open link?</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="space-y-4 pt-0 text-sm leading-relaxed">
        <p>Choose where to open this link.</p>
        <div className="relative rounded-md border border-border bg-background-2/50">
          <div className="max-h-32 overflow-y-auto px-3 py-2.5 pr-10 font-mono text-[13px] leading-relaxed break-all text-foreground">
            {url}
          </div>
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger
                render={
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    icon
                    className="absolute top-1.5 right-1.5"
                    aria-label={copied ? 'Link copied' : 'Copy link'}
                    onClick={() => void handleCopy()}
                  />
                }
              >
                {copied ? (
                  <Check className="size-4 text-foreground-success" />
                ) : (
                  <Copy className="size-4" />
                )}
              </Tooltip.Trigger>
              <Tooltip.Content>{copied ? 'Copied' : 'Copy link'}</Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        </div>
      </Dialog.Body>
      <Dialog.Footer className="flex-col-reverse sm:flex-col-reverse">
        <Button className="w-full" variant="secondary" onClick={controller.dismiss}>
          Cancel
        </Button>
        <Button
          className="w-full"
          variant="secondary"
          disabled={!canOpenInEmdashBrowser}
          onClick={() => controller.complete('emdash-browser')}
        >
          <Globe className="size-4" />
          Open in Hardcore
        </Button>
        <Button
          className="w-full"
          variant="primary"
          onClick={() => controller.complete('external-browser')}
        >
          <ExternalLink className="size-4" />
          Open in Browser
        </Button>
      </Dialog.Footer>
    </>
  );
}

export const confirmExternalLinkModal = defineModal<ExternalLinkChoice>()({
  id: 'confirmExternalLinkModal',
  component: ExternalLinkChoiceDialog,
  size: 'sm',
});
