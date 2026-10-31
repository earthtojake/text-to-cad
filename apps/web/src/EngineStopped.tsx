import { PlugZap } from 'lucide-react';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { translateIn } from '@text-to-cad/ui/i18n';

/**
 * What the page says when the engine that served it is gone (`isEngineGone`): it stopped, or the one
 * answering now does not know this page's token (`refused`: its link was replaced, by `cad server
 * --rotate-token`). Drawn over the page, which stays as it was while the page asks for its engine
 * again and reloads when it is back (`useEngineReconnect`).
 */
export function EngineStopped({ locale, refused = false }: { locale: string; refused?: boolean }) {
  return <div role="alert" className="absolute inset-0 z-50 bg-background">
    <EmptyState icon={PlugZap} title={translateIn(locale, refused ? 'app.engine.linkReplaced' : 'app.engine.notRunning')}
      description={translateIn(locale, refused ? 'app.engine.openNewLink' : 'app.engine.startIt')} tone="warn" />
  </div>;
}
