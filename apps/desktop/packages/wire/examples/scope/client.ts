import { createScope, describeScope } from '@emdash/shared/concurrency';
import { systemClock } from '@emdash/shared/scheduling';

async function main(): Promise<void> {
  const events: string[] = [];
  const root = createScope({
    label: 'root',
    clock: systemClock,
    onCleanupError: (error, scope) => {
      console.log('cleanup error:', scope.label, error instanceof Error ? error.message : error);
    },
  });
  const session = root.child('session');

  root.add(() => {
    events.push('root cleanup');
  });
  session.add(() => {
    events.push('session subscription cleanup');
  });
  session.use({
    dispose: () => {
      events.push('session resource dispose');
    },
  });
  const run = session.run('background refresh', async (signal) => {
    signal.addEventListener('abort', () => {
      events.push('run aborted');
    });
    await systemClock.sleep(0, { signal });
    if (signal.aborted) return;
    events.push('run completed');
  });

  console.log('active runs:', describeScope(root).children[0]?.runs);
  await run.exit;

  const cancelled = root.child('cancelled-session');
  const cancelledRun = cancelled.run('slow refresh', async (signal) => {
    signal.addEventListener('abort', () => {
      events.push('slow run aborted');
    });
    await systemClock.sleep(10, { signal });
  });
  await Promise.resolve();
  const dispose = cancelled.dispose('example cancellation');
  await cancelledRun.exit;
  await dispose;
  console.log('cancelled run:', await cancelledRun.exit);

  await root.dispose();

  root.add(() => {
    events.push('late cleanup');
  });

  console.log('scope disposed:', root.disposed);
  console.log('cleanup order:', events.join(' -> '));
}

void main();
