import { defineContract, fallible, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';
import { hostSettingsErrorSchema } from './errors';
import { hostSettingsStateSchema, updateHostSettingsInputSchema } from './schemas';

/**
 * The host-settings runtime (spec: activation-scripts-via-terminals): owns the
 * per-host defaults file in the host's emdash data directory. One file per host,
 * one live state — get/update verbs plus a live model that also reflects
 * out-of-band edits to the file (watched via the shared config-model machinery).
 */
export const hostSettingsContract = defineContract({
  /** Current settings; republished on every update and on out-of-band file edits. */
  state: liveModel({
    key: z.void().optional(),
    states: {
      current: liveState({ data: hostSettingsStateSchema }),
    },
  }),

  get: fallible({
    input: z.void().optional(),
    data: hostSettingsStateSchema,
    error: hostSettingsErrorSchema,
  }),

  /**
   * Partial write: merges the given fields into the file (null clears a field),
   * preserving unknown keys for forward compatibility. Returns the new state.
   */
  update: fallible({
    input: updateHostSettingsInputSchema,
    data: hostSettingsStateSchema,
    error: hostSettingsErrorSchema,
  }),
});

export type HostSettingsContract = typeof hostSettingsContract;
