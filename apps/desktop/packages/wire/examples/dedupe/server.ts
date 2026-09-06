import { compose, deduplicate } from '@emdash/shared/requests';
import {
  createController,
  client,
  connect,
  defineContract,
  memoryTransportPair,
  procedure,
  serve,
} from '@emdash/wire/rpc';
import { z } from 'zod';

const api = defineContract({
  expensiveStats: procedure({
    input: z.object({ repo: z.string(), branch: z.string() }),
    output: z.object({ repo: z.string(), branch: z.string(), executions: z.number() }),
  }),
});

async function main(): Promise<void> {
  let executions = 0;
  const pair = memoryTransportPair();
  const controller = createController(api, {
    expensiveStats: compose(
      async (input, _meta) => {
        executions += 1;
        const execution = executions;
        await sleep(10);
        return { ...input, executions: execution };
      },
      [deduplicate()]
    ),
  });
  serve(pair.right, controller);

  const contractClient = client(api, connect(pair.left));
  const [first, second, third] = await Promise.all([
    contractClient.expensiveStats({ repo: 'emdash', branch: 'main' }),
    contractClient.expensiveStats({ branch: 'main', repo: 'emdash' }),
    contractClient.expensiveStats({ repo: 'emdash', branch: 'feature' }),
  ]);

  console.log('first:', first);
  console.log('second:', second);
  console.log('third:', third);
  console.log('handler executions:', executions);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

void main();
