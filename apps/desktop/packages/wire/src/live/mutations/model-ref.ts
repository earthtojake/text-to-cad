import type { z } from 'zod';

export type LiveStateRef<
  Id extends string = string,
  KeySchema extends z.ZodTypeAny = z.ZodTypeAny,
  DataSchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  id: Id;
  keySchema: KeySchema;
  dataSchema: DataSchema;
};

export type LiveStateKey<Ref extends LiveStateRef> = z.infer<Ref['keySchema']>;

export type LiveStateData<Ref extends LiveStateRef> = z.infer<Ref['dataSchema']>;
