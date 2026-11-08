// The words the shell says where the CAD app cannot be loaded, which its build hands it
// (`scripts/shell-words.mjs`): `{ [locale]: { [key]: words } }`.
declare module 'virtual:cad-shell-words' {
  const words: Record<string, Record<string, string>>;
  export default words;
}
