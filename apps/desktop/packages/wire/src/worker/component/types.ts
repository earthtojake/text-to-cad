import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import type { z } from 'zod';
import type { ContractClient } from '../../api/client';
import type { Controller } from '../../api/controller';
import type { Contract, ContractDefinitions } from '../../api/define';

export type WireComponentContractRequirement<Defs extends ContractDefinitions> = {
  readonly kind: 'contract';
  readonly contract: Contract<Defs>;
};

export type WireComponentRequirement = WireComponentContractRequirement<ContractDefinitions>;

export type WireComponentRequirements = Record<string, WireComponentRequirement>;

export type ResolvedWireComponentRequirements<Requirements extends WireComponentRequirements> = {
  [Key in keyof Requirements]: Requirements[Key] extends WireComponentContractRequirement<
    infer Defs
  >
    ? ContractClient<Defs>
    : never;
};

export type ProvidedWireComponentRequirements<Requirements extends WireComponentRequirements> = {
  [Key in keyof Requirements]: Requirements[Key] extends WireComponentContractRequirement<
    infer Defs
  >
    ? ContractClient<Defs> | Controller
    : never;
};

export type WireComponentInstance<Defs extends ContractDefinitions> = {
  readonly client: ContractClient<Defs>;
  dispose(): Promise<void>;
};

export type WireComponentCreateOptions<Requirements extends WireComponentRequirements, Config> = {
  scope: Scope;
  dependencies: ResolvedWireComponentRequirements<Requirements>;
  config: Config;
  logger?: Logger;
};

export type WireComponentCreateContext<
  Defs extends ContractDefinitions,
  Requirements extends WireComponentRequirements,
  Config,
> = {
  scope: Scope;
  dependencies: ResolvedWireComponentRequirements<Requirements>;
  config: Config;
  logger: Logger;
  signal: AbortSignal;
  instance(options: { scope: Scope; controller: Controller }): WireComponentInstance<Defs>;
};

export type WireComponentDefinition<
  Id extends string,
  Defs extends ContractDefinitions,
  Requirements extends WireComponentRequirements,
  Config,
> = {
  readonly id: Id;
  readonly contract: Contract<Defs>;
  readonly requirements: Requirements;
  readonly configSchema: z.ZodType<Config>;
  create(options: WireComponentCreateOptions<Requirements, Config>): WireComponentInstance<Defs>;
};

export type DefineWireComponentOptions<
  Id extends string,
  Defs extends ContractDefinitions,
  Requirements extends WireComponentRequirements,
  Config,
> = {
  id: Id;
  contract: Contract<Defs>;
  requirements: Requirements;
  configSchema: z.ZodType<Config>;
  create(
    context: WireComponentCreateContext<Defs, Requirements, Config>
  ): WireComponentInstance<Defs>;
};
