import { describe, expect, it } from 'vitest';
import { machineFormSchema, type MachineFormValues } from './machine-form-schema';

const baseValues: MachineFormValues = {
  name: 'Conn',
  host: 'dev.internal',
  port: 22,
  username: 'alice',
  authType: 'agent',
  password: '',
  privateKeyPath: '',
  passphrase: '',
  sshConfigAlias: '',
  forwardAgent: false,
  proxyJump: '',
  proxyCommand: '',
  isEditing: false,
};

describe('machineFormSchema', () => {
  it.each([
    ['name', ' Conn', 'Connection name cannot start or end with spaces'],
    ['host', 'dev.internal ', 'Host cannot start or end with spaces'],
    ['username', ' alice', 'Username cannot start or end with spaces'],
    ['privateKeyPath', '~/.ssh/id_rsa ', 'Private key path cannot start or end with spaces'],
    ['sshConfigAlias', ' corp-dev', 'SSH config alias cannot start or end with spaces'],
    ['proxyJump', 'bastion ', 'ProxyJump cannot start or end with spaces'],
  ] as const)('rejects leading or trailing spaces in %s', (field, value, message) => {
    const result = machineFormSchema.safeParse({
      ...baseValues,
      authType: field === 'privateKeyPath' ? 'key' : baseValues.authType,
      privateKeyPath: field === 'privateKeyPath' ? value : baseValues.privateKeyPath,
      [field]: value,
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toEqual(
      expect.arrayContaining([expect.objectContaining({ path: [field], message })])
    );
  });

  it('allows spaces inside fields that can contain composite values', () => {
    expect(
      machineFormSchema.safeParse({
        ...baseValues,
        name: 'Staging Server',
        proxyJump: 'alice@bastion:2222,bob@internal-bastion:2222',
      }).success
    ).toBe(true);
  });

  it('does not reject leading or trailing spaces in password credentials', () => {
    expect(
      machineFormSchema.safeParse({
        ...baseValues,
        authType: 'password',
        password: ' secret ',
      }).success
    ).toBe(true);
    expect(
      machineFormSchema.safeParse({
        ...baseValues,
        authType: 'key',
        privateKeyPath: '~/.ssh/id_rsa',
        passphrase: ' secret ',
      }).success
    ).toBe(true);
  });

  it('allows alias-backed key auth without a manually entered private key path', () => {
    expect(
      machineFormSchema.safeParse({
        ...baseValues,
        username: '',
        authType: 'key',
        privateKeyPath: '',
        sshConfigAlias: 'corp-dev',
      }).success
    ).toBe(true);
  });

  it('still requires a private key path for manual key auth', () => {
    const result = machineFormSchema.safeParse({
      ...baseValues,
      authType: 'key',
      privateKeyPath: '',
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toEqual(
      expect.arrayContaining([expect.objectContaining({ path: ['privateKeyPath'] })])
    );
  });

  it('requires username and password for manual password auth', () => {
    const result = machineFormSchema.safeParse({
      ...baseValues,
      username: '',
      authType: 'password',
      password: '',
      isEditing: false,
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: ['username'] }),
        expect.objectContaining({ path: ['password'] }),
      ])
    );
  });

  it('allows SSH config aliases that are not valid hostnames', () => {
    expect(
      machineFormSchema.safeParse({
        ...baseValues,
        host: 'team/foo%bar@corp',
        username: '',
        sshConfigAlias: 'team/foo%bar@corp',
      }).success
    ).toBe(true);
  });

  it('validates the persisted SSH config alias instead of the display host', () => {
    const result = machineFormSchema.safeParse({
      ...baseValues,
      host: 'dev.internal',
      username: '',
      sshConfigAlias: '-oProxyCommand=evil',
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toEqual(
      expect.arrayContaining([expect.objectContaining({ path: ['sshConfigAlias'] })])
    );
  });

  it('still rejects invalid hostnames for manual connections', () => {
    const result = machineFormSchema.safeParse({
      ...baseValues,
      host: 'team/foo%bar@corp',
      sshConfigAlias: '',
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toEqual(
      expect.arrayContaining([expect.objectContaining({ path: ['host'] })])
    );
  });
});
