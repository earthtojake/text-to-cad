import { ok } from '@emdash/shared';
import {
  defineContract,
  liveModel,
  liveState,
  liveLog,
  mutation,
  procedure,
} from '@emdash/wire/rpc';
import { z } from 'zod';

export const sessionKeySchema = z.object({ sessionId: z.string() });
export const noteSchema = z.object({ id: z.string(), text: z.string() });
export const notesStateSchema = z.object({ notes: z.array(noteSchema) });

export type SessionKey = z.infer<typeof sessionKeySchema>;
export type NotesState = z.infer<typeof notesStateSchema>;

export const notesApi = defineContract({
  activity: liveLog({ key: sessionKeySchema }),
  session: liveModel({
    key: sessionKeySchema,
    states: {
      notes: liveState({ data: notesStateSchema }),
    },
    mutations: {
      addNote: mutation(
        {
          input: z.object({ text: z.string() }),
          data: noteSchema,
          error: z.string(),
        },
        (ctx, input) => {
          const note = { id: input.text.toLowerCase().replace(/\s+/g, '-'), text: input.text };
          ctx.produce('notes', (draft) => {
            (draft as NotesState).notes.push(note);
          });
          return ok(note);
        }
      ),
    },
  }),
  clearNotes: procedure({
    input: sessionKeySchema,
    output: notesStateSchema,
  }),
});
