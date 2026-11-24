import { useEffect, useState, type ReactNode } from 'react';
import { EmptyState, StatusAction } from '@cad/ui/navigation';
import { translateIn } from '@cad/ui/i18n';
import { isShareSecret, SHARE_UNREADABLE, SHARE_UNSUPPORTED } from '@cad/core/client';
import { deleteShare, SHARE_GONE } from './host/share.js';

/** A share's page that is no view: the app's status screen, alone on the page (`docs/viewer-ux.md`). */
function SharePage({ state, children }: { state: string; children: ReactNode }) {
  const asking = state === 'ask' || state === 'deleting';
  return <div role={asking ? undefined : 'alert'} className="fixed inset-0 overflow-hidden bg-background" data-share-state={state}>{children}</div>;
}

/**
 * Why a shared model's view did not open, in the person's terms: it is gone (the service has none: it
 * expired, 7 days after it was last shared, or was deleted), its link is incomplete or damaged (no key, the
 * wrong one, or bytes damaged: one case), it is in a form this viewer does not read, or anything else, which
 * may pass, with Retry.
 */
export function ShareFailed({ error, locale, onRetry }: { error: unknown; locale: string; onRetry: () => void }) {
  const say = (key: string) => translateIn(locale, key);
  const code = (error as { code?: string } | null)?.code;
  const detail = error instanceof Error ? error.message : String(error);
  if (code === SHARE_GONE) return <SharePage state="gone"><EmptyState title={say('share.gone.title')} description={say('share.gone.detail')} /></SharePage>;
  if (code === SHARE_UNREADABLE) {
    return <SharePage state="damaged"><EmptyState title={say('share.damaged.title')} description={say('share.damaged.detail')} /></SharePage>;
  }
  if (code === SHARE_UNSUPPORTED) return <SharePage state="unsupported"><EmptyState title={say('share.unsupported.title')} description={detail} /></SharePage>;
  return <SharePage state="failed"><EmptyState title={say('share.failed.title')} description={detail}
    action={<StatusAction onClick={onRetry}>{say('share.retry')}</StatusAction>} /></SharePage>;
}

type DeleteState = 'ask' | 'deleting' | 'deleted' | 'gone' | 'refused' | 'failed';

/**
 * The page a share's delete link opens (`/<id>#delete=<secret>`): it asks first, as deleting takes the link
 * from everyone, and its one action sends the deletion, the secret in its `Authorization` alone
 * (`host/share.js`). Then it says what came of it: deleted, already gone (404), or not this share's link
 * (403); any other failure offers the action again. A secret the link cuts short is never sent.
 */
export function ShareDelete({ id, secret, locale }: { id: string; secret: string; locale: string }) {
  const say = (key: string) => translateIn(locale, key);
  const [state, setState] = useState<DeleteState>('ask');
  const [detail, setDetail] = useState('');
  useEffect(() => { document.title = say('share.delete.pageTitle'); });
  if (!isShareSecret(secret)) {
    return <SharePage state="damaged"><EmptyState title={say('share.damaged.title')} description={say('share.damaged.detail')} /></SharePage>;
  }
  const send = () => {
    setState('deleting');
    deleteShare(id, secret).then(setState, (error: unknown) => {
      setDetail(error instanceof Error ? error.message : String(error));
      setState('failed');
    });
  };
  if (state === 'deleted') return <SharePage state="deleted"><EmptyState title={say('share.deleted.title')} description={say('share.deleted.detail')} /></SharePage>;
  if (state === 'gone') return <SharePage state="gone"><EmptyState title={say('share.delete.gone.title')} description={say('share.delete.gone.detail')} /></SharePage>;
  if (state === 'refused') {
    return <SharePage state="refused"><EmptyState title={say('share.delete.refused.title')} description={say('share.delete.refused.detail')} /></SharePage>;
  }
  const failed = state === 'failed';
  return <SharePage state={state}>
    <EmptyState title={say(failed ? 'share.delete.failed.title' : 'share.delete.title')} description={failed ? detail : say('share.delete.detail')}
      action={<StatusAction onClick={send} disabled={state === 'deleting'} data-share-delete="">
        {say(state === 'deleting' ? 'share.delete.deleting' : failed ? 'share.retry' : 'share.delete.action')}
      </StatusAction>} />
  </SharePage>;
}
