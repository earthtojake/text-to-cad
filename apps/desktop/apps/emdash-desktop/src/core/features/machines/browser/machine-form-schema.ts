import * as z from 'zod';

const manualHostPattern = /^[a-zA-Z0-9._\-[\]:]+$/;
const sshAliasPattern = /^[A-Za-z0-9._@%+:/[\]-]+$/;

function hasLeadingOrTrailingWhitespace(value: string): boolean {
  return value !== value.trim();
}

function addWhitespaceIssue(
  ctx: z.RefinementCtx,
  path: 'name' | 'host' | 'username' | 'privateKeyPath' | 'sshConfigAlias' | 'proxyJump',
  label: string
): void {
  ctx.addIssue({
    code: z.ZodIssueCode.custom,
    message: `${label} cannot start or end with spaces`,
    path: [path],
  });
}

export const machineFormSchema = z
  .object({
    name: z.string().min(1, 'Name is required'),
    host: z.string().min(1, 'Host is required'),
    port: z
      .number()
      .int()
      .min(1, 'Port must be at least 1')
      .max(65535, 'Port must be at most 65535'),
    username: z.string(),
    authType: z.enum(['password', 'key', 'agent']),
    password: z.string(),
    privateKeyPath: z.string(),
    passphrase: z.string(),
    sshConfigAlias: z.string(),
    forwardAgent: z.boolean(),
    proxyJump: z.string(),
    proxyCommand: z.string(),
    isEditing: z.boolean(),
  })
  .superRefine((val, ctx) => {
    if (hasLeadingOrTrailingWhitespace(val.name)) {
      addWhitespaceIssue(ctx, 'name', 'Connection name');
    }
    if (hasLeadingOrTrailingWhitespace(val.host)) {
      addWhitespaceIssue(ctx, 'host', 'Host');
    }
    if (hasLeadingOrTrailingWhitespace(val.username)) {
      addWhitespaceIssue(ctx, 'username', 'Username');
    }
    if (hasLeadingOrTrailingWhitespace(val.privateKeyPath)) {
      addWhitespaceIssue(ctx, 'privateKeyPath', 'Private key path');
    }
    if (hasLeadingOrTrailingWhitespace(val.sshConfigAlias)) {
      addWhitespaceIssue(ctx, 'sshConfigAlias', 'SSH config alias');
    }
    if (hasLeadingOrTrailingWhitespace(val.proxyJump)) {
      addWhitespaceIssue(ctx, 'proxyJump', 'ProxyJump');
    }

    if (val.sshConfigAlias) {
      if (
        !hasLeadingOrTrailingWhitespace(val.sshConfigAlias) &&
        (val.sshConfigAlias.startsWith('-') || !sshAliasPattern.test(val.sshConfigAlias))
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Invalid SSH config alias',
          path: ['sshConfigAlias'],
        });
      }
    } else if (!hasLeadingOrTrailingWhitespace(val.host) && !manualHostPattern.test(val.host)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Invalid hostname or IP address',
        path: ['host'],
      });
    }
    if (!val.sshConfigAlias && !val.username) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Username is required',
        path: ['username'],
      });
    }
    if (val.authType === 'password' && !val.password && !val.isEditing) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Password is required',
        path: ['password'],
      });
    }
    if (val.authType === 'key' && !val.sshConfigAlias && !val.privateKeyPath) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Private key path is required',
        path: ['privateKeyPath'],
      });
    }
  });

export type MachineFormValues = z.infer<typeof machineFormSchema>;
