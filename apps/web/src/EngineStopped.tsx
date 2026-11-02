import { PlugZap } from 'lucide-react';
import { EmptyState } from '@cad/ui/navigation';
import { Button } from '@cad/ui/primitives/button';
import { translateIn } from '@cad/ui/i18n';

/**
 * What the page says when the engine that served it is gone (`isEngineGone`): CAD is not running
 * (it stopped, or the machine restarted), or the one answering now does not know this page's token
 * (`refused`: its link was replaced, by `cad server --rotate-token`). Said in a person's terms, with
 * the one thing they can do: a person never starts the engine by hand -- an agent showing a model or
 * the CAD app opening does -- so the page names that, reconnects on its own meanwhile
 * (`useEngineReconnect`), and offers a reload for whoever would rather press something. A replaced
 * link has no reload worth offering: the new link is the way back.
 */
export function EngineStopped({ locale, refused = false }: { locale: string; refused?: boolean }) {
  const say = (key: string) => translateIn(locale, key);
  return <div role="alert" className="absolute inset-0 z-50 bg-background">
    <EmptyState icon={PlugZap} title={say(refused ? 'app.engine.linkReplaced' : 'app.engine.notRunning')}
      description={say(refused ? 'app.engine.openNewLink' : 'app.engine.startIt')} tone="warn"
      action={refused ? null : <Button type="button" variant="outline" size="sm" onClick={() => window.location.reload()}>{say('app.engine.reload')}</Button>} />
  </div>;
}
