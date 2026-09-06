import { defineContract, fallible, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import { hostRuntimesDefinitions } from '#services/runtime-broker/api';
import { portForwardsContract } from '../port-forwards/contract';
import {
  wireHealthSchema,
  wireInitializeInputSchema,
  wireInitializeResultSchema,
  wireProtocolIncompatibleSchema,
} from './schemas';

export const workspaceWireContract = defineContract({
  health: procedure({ input: z.void().optional(), output: wireHealthSchema }),
  initialize: fallible({
    input: wireInitializeInputSchema,
    data: wireInitializeResultSchema,
    error: wireProtocolIncompatibleSchema,
  }),
  ...hostRuntimesDefinitions,
  portForwards: portForwardsContract,
});
