import { createMailbox, createScope } from '@emdash/shared/concurrency';

async function main(): Promise<void> {
  const scope = createScope({ label: 'mailbox-example' });
  const mailbox = scope.use(createMailbox<string>({ capacity: 2 }));
  const seen: string[] = [];

  const consumer = scope.run('drain-mailbox', async () => {
    for await (const value of mailbox) {
      seen.push(value);
    }
  });

  await mailbox.offer('first');
  await mailbox.offer('second');
  mailbox.close();
  await consumer.value();

  console.log('drained:', seen.join(', '));

  const bounded = createMailbox<string>({ capacity: 1, overflow: 'reject' });
  console.log('first offer:', bounded.tryOffer('kept').kind);
  console.log('second offer:', bounded.tryOffer('rejected').kind);
  bounded.dispose();

  await scope.dispose();
}

void main();
