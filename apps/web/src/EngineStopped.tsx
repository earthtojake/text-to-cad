import { PlugZap } from 'lucide-react';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { translateIn } from '@text-to-cad/ui/i18n';

/**
 * What the page says when the engine that served it is gone (`isEngineGone`): it stopped, or the one
 * answering now does not know this page's token. Drawn over the page, which stays as it was, and
 * gone with the next read that answers.
 */
export function EngineStopped({ locale }: { locale: string }) {
  return <div role="alert" className="absolute inset-0 z-50 bg-background">
    <EmptyState icon={PlugZap} title={translateIn(locale, 'app.engine.notRunning')} description={translateIn(locale, 'app.engine.runAgain')} tone="warn" />
  </div>;
}
