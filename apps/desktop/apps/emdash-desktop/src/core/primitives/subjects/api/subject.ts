import { z } from 'zod';

declare const subjectBrand: unique symbol;

export interface Subject<TKind extends string = string> {
  readonly kind: TKind;
  readonly key: string;
  readonly [subjectBrand]: TKind;
}

export interface SubjectRetention {
  readonly maxAge?: number;
  readonly maxEntries?: number;
}

export interface SubjectDef<TKind extends string, TKeySchema extends z.ZodType> {
  (key: z.input<TKeySchema>): Subject<TKind>;
  readonly kind: TKind;
  readonly keySchema: TKeySchema;
  readonly retention: SubjectRetention | undefined;
  encode(key: z.input<TKeySchema>): string;
  is(subject: Subject): subject is Subject<TKind>;
}

export interface DefineSubjectOptions<TKind extends string, TKeySchema extends z.ZodType> {
  readonly kind: TKind;
  readonly key: TKeySchema;
  readonly encode: (key: z.output<TKeySchema>) => string;
  readonly retention?: SubjectRetention;
}

export const subjectSchema = z
  .object({
    kind: z.string().min(1),
    key: z.string(),
  })
  .transform((subject) => subject as Subject);

export function defineSubject<TKind extends string, TKeySchema extends z.ZodType>(
  options: DefineSubjectOptions<TKind, TKeySchema>
): SubjectDef<TKind, TKeySchema> {
  const encode = (key: z.input<TKeySchema>): string => options.encode(options.key.parse(key));
  const create = (key: z.input<TKeySchema>): Subject<TKind> =>
    ({
      kind: options.kind,
      key: encode(key),
    }) as Subject<TKind>;

  return Object.assign(create, {
    kind: options.kind,
    keySchema: options.key,
    retention: options.retention,
    encode,
    is: (subject: Subject): subject is Subject<TKind> => subject.kind === options.kind,
  });
}

export const appSubject = defineSubject({
  kind: 'app',
  key: z.object({}),
  encode: () => '',
});
