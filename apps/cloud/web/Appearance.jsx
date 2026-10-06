import { Monitor, Moon, Sun } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@text-to-cad/ui/primitives/select';
import { COLOR_SCHEMES } from './host/colorScheme.ts';

const ICONS = { system: Monitor, light: Sun, dark: Moon };

/** The page's appearance (System, Light, Dark), placed beside Projection in the Display panel: the host's own control. */
/** @param {{ preference: 'system' | 'light' | 'dark', mode: 'light' | 'dark', onChange: (value: string) => void }} props */
export default function Appearance({ preference, mode, onChange }) {
  const displayed = preference === 'system' ? mode : preference;
  const Icon = ICONS[displayed] || Sun;
  return <Select value={preference} onValueChange={onChange}>
    <SelectTrigger aria-label="Appearance" size="sm" className="!h-7 min-w-0 gap-1 px-2 !text-tiny [&_svg]:size-3.5">
      <span className="flex min-w-0 items-center gap-1"><Icon className="size-3.5 shrink-0" aria-hidden="true" /><SelectValue>{displayed === 'dark' ? 'Dark' : 'Light'}</SelectValue></span>
    </SelectTrigger>
    <SelectContent>
      {COLOR_SCHEMES.map(option => {
        const OptionIcon = ICONS[option.id];
        return <SelectItem key={option.id} value={option.id} icon={<OptionIcon className="size-3.5" />}>{option.label}</SelectItem>;
      })}
    </SelectContent>
  </Select>;
}
