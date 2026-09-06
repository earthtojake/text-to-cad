import { style } from '@vanilla-extract/css';

export {
  menuContent,
  menuItem,
  menuLabel,
  menuSeparator,
  positioner,
} from '../dropdown-menu/dropdown-menu.css';

export const contextMenuContent = style({
  width: 'auto',
  minWidth: '10rem',
});
