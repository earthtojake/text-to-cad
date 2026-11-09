// The words the shell says where the CAD app itself cannot be loaded (src/host/shell.ts): the app's own
// notice (src/host/unreachable.js), every locale's, read from @cad/ui's dictionaries as the shell is built and
// handed to it as `virtual:cad-shell-words`, so the shell stays a few kilobytes and carries no dictionary.
// The shell's build and its tests both read the module through this plugin.
import { LOCALES, translateIn } from '@cad/ui/i18n';
import { UNREACHABLE_KEYS } from '../src/host/unreachable.js';

const ID = 'virtual:cad-shell-words';

/** `{ [locale]: { [key]: words } }`: each locale's words for the shell's notice. */
export function shellWordsTable() {
  return Object.fromEntries(LOCALES.map(locale => [locale,
    Object.fromEntries(UNREACHABLE_KEYS.map(key => [key, translateIn(locale, key)]))]));
}

export function shellWords() {
  return {
    name: 'cad-shell-words',
    resolveId(id) { return id === ID ? `\0${ID}` : undefined; },
    load(id) { return id === `\0${ID}` ? `export default ${JSON.stringify(shellWordsTable())};\n` : undefined; },
  };
}
