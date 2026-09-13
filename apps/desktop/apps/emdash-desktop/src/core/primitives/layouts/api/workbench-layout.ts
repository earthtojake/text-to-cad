import { defineLayout, slot } from './define-layout';

export const workbenchLayout = defineLayout({
  id: 'workbench',
  slots: {
    wrap: slot.wrapper(),
    titlebar: slot.optional(),
    main: slot.main(),
  },
});
