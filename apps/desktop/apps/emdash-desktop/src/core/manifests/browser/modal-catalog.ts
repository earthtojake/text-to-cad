import { defineModalCatalog } from '@core/primitives/modals/react';
import { featureModalDefs } from './browser-contributions';

export const modalCatalog = defineModalCatalog(featureModalDefs);

export type ModalCatalog = typeof modalCatalog;
