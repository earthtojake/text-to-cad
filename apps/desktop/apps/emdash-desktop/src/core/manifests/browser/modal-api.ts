import type { ModalCatalog } from '@core/manifests/browser/modal-catalog';
import {
  createModalApi,
  type ModalApiTransport,
  type ModalIdOf,
} from '@core/primitives/modals/react';
import { modalStore } from '@core/primitives/modals/react/modal-store';

// Keep ModalCatalog type-only: runtime catalog imports load every modal component.
const modalTransport: ModalApiTransport = {
  open: (id, props) => modalStore.open(id, props),
};

export const { openModal, useOpenModal, useModalController } =
  createModalApi<ModalCatalog>(modalTransport);

export type ModalId = ModalIdOf<ModalCatalog>;
