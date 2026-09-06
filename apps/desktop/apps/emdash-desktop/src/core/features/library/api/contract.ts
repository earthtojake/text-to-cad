import { defineContract, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import type { PromptLibraryPrompt } from '@core/primitives/prompt-library/api';

export const promptLibraryDomain = 'promptLibrary' as const;

export const promptLibraryContract = defineContract({
  get: procedure({ input: z.void(), output: z.custom<PromptLibraryPrompt[]>() }),
  update: procedure({
    input: z.object({ prompts: z.custom<PromptLibraryPrompt[]>() }),
    output: z.void(),
  }),
});
