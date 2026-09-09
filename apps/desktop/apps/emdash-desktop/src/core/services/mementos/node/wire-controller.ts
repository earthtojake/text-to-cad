import { createController, type Controller } from '@emdash/wire/rpc';
import { mementosWireContract } from '@core/primitives/mementos/api';
import type { MementoService } from './memento-service';

export function createMementosWireController(service: MementoService): Controller {
  return createController(mementosWireContract, {
    memento: service.host,
    deleteBySubject: (subject) => service.deleteBySubject(subject),
    deleteAll: () => service.deleteAll(),
    deleteOrphans: ({ kind, validKeys }) => service.deleteOrphans(kind, validKeys),
  });
}
