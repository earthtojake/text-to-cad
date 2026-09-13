import {
  buildController,
  type Controller,
  type DownloadFileImpl,
  type ProcedureHandler,
  type UploadFileImpl,
} from '../api/controller';
import type {
  Contract,
  ContractDefinitions,
  DownloadFileEndpointDef,
  EndpointDef,
  EventStreamEndpointDef,
  LiveJobEndpointDef,
  LiveLogEndpointDef,
  LiveModelDef,
  ProcedureDef,
  UploadFileEndpointDef,
} from '../api/define';
import type { ValidatePolicy } from '../api/validation';
import {
  liveEndpointKinds,
  type EventStreamEntryImpl,
  type LiveJobEntryImpl,
  type LiveLogEntryImpl,
  type LiveModelEntryImpl,
} from '../live/endpoint-kinds';

type EndpointImpl<Def extends EndpointDef> = Def extends ProcedureDef
  ? ProcedureHandler<Def>
  : Def extends LiveLogEndpointDef
    ? LiveLogEntryImpl<Def>
    : Def extends EventStreamEndpointDef
      ? EventStreamEntryImpl<Def>
      : Def extends LiveModelDef
        ? LiveModelEntryImpl<Def>
        : Def extends LiveJobEndpointDef
          ? LiveJobEntryImpl<Def>
          : Def extends DownloadFileEndpointDef
            ? DownloadFileImpl<Def>
            : Def extends UploadFileEndpointDef
              ? UploadFileImpl<Def>
              : never;

export type ContractImpl<Defs extends ContractDefinitions> = {
  [Name in keyof Defs]?: Defs[Name] extends EndpointDef
    ? EndpointImpl<Defs[Name]>
    : Defs[Name] extends Contract<infer Nested>
      ? ContractImpl<Nested>
      : never;
};

export type CreateControllerOptions = {
  /**
   * Contract validation policy. Defaults to the environment rule: `'full'`
   * (inputs + outputs) outside production, `'inputs'` in production.
   */
  validate?: ValidatePolicy;
};

export function createController<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  impl: ContractImpl<Defs>,
  options: CreateControllerOptions = {}
): Controller {
  return buildController(contract, impl, {
    liveEndpoints: liveEndpointKinds,
    validate: options.validate,
  });
}
