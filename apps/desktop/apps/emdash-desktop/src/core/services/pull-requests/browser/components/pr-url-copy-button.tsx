import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { Check, Copy } from 'lucide-react';
import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { cn } from '@core/primitives/styling/browser/cn';
import { copyPrUrl } from './pr-url-copy';

interface PrUrlCopyButtonProps {
  url: string;
  className?: string;
}

export function PrUrlCopyButton({ url, className }: PrUrlCopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const resetTimerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (resetTimerRef.current !== null) window.clearTimeout(resetTimerRef.current);
    },
    []
  );

  const handleCopy = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    const copySucceeded = await copyPrUrl(url);
    if (!copySucceeded) {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
        resetTimerRef.current = null;
      }
      setCopied(false);
      return;
    }

    setCopied(true);
    if (resetTimerRef.current !== null) window.clearTimeout(resetTimerRef.current);
    resetTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      resetTimerRef.current = null;
    }, 1500);
  };

  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <Button
            type="button"
            aria-label={copied ? 'PR URL copied' : 'Copy PR URL'}
            variant="ghost"
            size="xs"
            icon
            className={cn('cursor-pointer', className, copied && 'opacity-100')}
            onClick={handleCopy}
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          </Button>
        }
      />
      <Tooltip.Content>{copied ? 'Copied!' : 'Copy PR URL'}</Tooltip.Content>
    </Tooltip.Root>
  );
}
