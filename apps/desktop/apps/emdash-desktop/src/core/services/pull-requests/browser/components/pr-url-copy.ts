import { toast } from '@emdash/ui/react/primitives';
import { copyTextToClipboard } from '@core/primitives/desktop-host/browser/host-client';

export async function copyPrUrl(url: string): Promise<boolean> {
  try {
    const result = await copyTextToClipboard(url);
    if (!result.success) {
      showCopyFailure();
      return false;
    }

    toast('PR URL copied');
    return true;
  } catch {
    showCopyFailure();
    return false;
  }
}

function showCopyFailure(): void {
  toast.error('Copy failed', { description: 'The PR URL could not be copied to the clipboard.' });
}
